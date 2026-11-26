"""Визуальная одометрия по паре кадров.

Алгоритм: ORB-признаки, ratio test, essential-матрица через
USAC_MAGSAC (или RANSAC) и recoverPose. Кадры приводятся к одной
высоте, чтобы масштаб пикселей совпадал, а перед детекцией
применяется CLAHE — на пасмурных и сумеречных кадрах обычный ORB
даёт слишком мало устойчивых точек.

Важно: `recoverPose` возвращает нормированный вектор переноса, то
есть длину шага в условных единицах, а не в метрах. Модуль честно
помечает это в результате (`units: "relative"`); метры появляются
только как грубая оценка в placeProfileService.

Пары с размытием, малым числом совпадений или слабой геометрией
не дают позу: estimate() возвращает None, а estimate_with_reason()
дополнительно сообщает причину (blur / few_matches / degenerate).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


TARGET_HEIGHT = 960

# Порог дисперсии лапласиана. Слишком высокий отбрасывал нормальные
# кадры с движением, поэтому он снижен, а слабые кадры дополнительно
# спасает CLAHE.
MIN_BLUR = 8.0

# Больше признаков и мягче ratio: последовательные кадры видео часто
# имеют малый базис и повторяющийся текстурированный фон.
ORB_FEATURES = 2500
RATIO_TEST = 0.75
RATIO_RETRY = 0.85

MIN_MATCHES = 12
MIN_INLIERS = 20
MIN_QUALITY = 0.12

# Абсолютное число инлайеров важнее доли: на текстурированной сцене
# совпадений может быть больше тысячи, и доля падает, хотя геометрия
# надёжная.
STRONG_INLIERS = 100

RANSAC_THRESHOLD = 1.5
RANSAC_PROB = 0.999

# USAC_MAGSAC устойчивее RANSAC на вырожденных сценах, но есть не во
# всех сборках OpenCV.
RANSAC_METHOD = getattr(cv2, "USAC_MAGSAC", cv2.RANSAC)

# Функция получает цветной кадр в рабочем разрешении и возвращает
# маску uint8: 255 — рабочие пиксели, 0 — динамические объекты.
DynamicMaskFn = Callable[[np.ndarray], np.ndarray | None]


class VisualOdometry:
    """Оценка относительной позы между двумя кадрами."""

    def __init__(
        self,
        camera_matrix: np.ndarray,
        dynamic_mask_fn: DynamicMaskFn | None = None,
    ) -> None:
        """Сохранить матрицу камеры и необязательную функцию масок."""

        matrix = np.asarray(camera_matrix, dtype=np.float64)

        if matrix.shape != (3, 3):
            raise ValueError(
                "camera_matrix должна быть матрицей 3×3."
            )

        self.camera_matrix = matrix
        self.dynamic_mask_fn = dynamic_mask_fn

        # Время подэтапов последнего вызова, миллисекунды.
        self.timings: dict[str, int] = {}

        # Причина последнего отказа: blur / few_matches / degenerate.
        self.last_reason: str | None = None

        # Диагностика последнего вызова: признаки, совпадения, инлайеры.
        self.diagnostics: dict = {}

    def estimate(
        self,
        frame_a: Path,
        frame_b: Path,
    ) -> dict | None:
        """Оценить позу между кадрами или вернуть None."""

        result, _ = self.estimate_with_reason(frame_a, frame_b)
        return result

    def estimate_with_reason(
        self,
        frame_a: Path,
        frame_b: Path,
    ) -> tuple[dict | None, str | None]:
        """Оценить позу и вернуть причину отказа второй величиной."""

        self.timings = {}
        self.last_reason = None
        self.diagnostics = {}

        image_a = _read_image(frame_a)
        image_b = _read_image(frame_b)

        color_a, color_b, gray_a, gray_b, scale = _prepare_pair(
            image_a,
            image_b,
        )

        blur_a = _blur_score(gray_a)
        blur_b = _blur_score(gray_b)

        self.diagnostics.update({
            "blur_a": round(float(blur_a), 2),
            "blur_b": round(float(blur_b), 2),
        })

        if blur_a < MIN_BLUR or blur_b < MIN_BLUR:
            return self._fail("blur")

        mask_a = self._mask(color_a)
        mask_b = self._mask(color_b)

        # CLAHE выравнивает локальный контраст: на видео с пасмурной
        # погодой это заметно повышает число устойчивых ORB-точек.
        equalized_a = _equalize(gray_a)
        equalized_b = _equalize(gray_b)

        started = time.perf_counter()

        orb = cv2.ORB_create(
            nfeatures=ORB_FEATURES,
            scaleFactor=1.2,
            nlevels=8,
            edgeThreshold=19,
            fastThreshold=12,
        )
        keypoints_a, descriptors_a = orb.detectAndCompute(
            equalized_a,
            mask_a,
        )
        keypoints_b, descriptors_b = orb.detectAndCompute(
            equalized_b,
            mask_b,
        )

        self.timings["orb"] = _elapsed_ms(started)

        features_a = len(keypoints_a or [])
        features_b = len(keypoints_b or [])

        self.diagnostics.update({
            "features_a": features_a,
            "features_b": features_b,
        })

        if (
            descriptors_a is None
            or descriptors_b is None
            or features_a < 2
            or features_b < 2
        ):
            return self._fail("few_matches")

        started = time.perf_counter()

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        good = _match(
            matcher,
            descriptors_a,
            descriptors_b,
            RATIO_TEST,
        )

        if len(good) < MIN_MATCHES:
            # Мягкий повтор: иногда строгий ratio оставляет 5–10
            # совпадений, которых не хватает для RANSAC.
            good = _match(
                matcher,
                descriptors_a,
                descriptors_b,
                RATIO_RETRY,
            )

        self.timings["match"] = _elapsed_ms(started)
        self.diagnostics["matches"] = len(good)

        if len(good) < MIN_MATCHES:
            return self._fail("few_matches")

        points_a = np.float32([
            keypoints_a[match.queryIdx].pt
            for match in good
        ])
        points_b = np.float32([
            keypoints_b[match.trainIdx].pt
            for match in good
        ])

        matrix = self._scaled_camera(scale)

        started = time.perf_counter()

        essential, inlier_mask = cv2.findEssentialMat(
            points_a,
            points_b,
            cameraMatrix=matrix,
            method=RANSAC_METHOD,
            prob=RANSAC_PROB,
            threshold=RANSAC_THRESHOLD,
        )

        self.timings["essential"] = _elapsed_ms(started)

        essential = _single_matrix(essential)

        if essential is None:
            return self._fail("degenerate")

        started = time.perf_counter()

        try:
            inliers, rotation, translation, _ = cv2.recoverPose(
                essential,
                points_a,
                points_b,
                matrix,
            )

        except cv2.error:
            self.timings["recover_pose"] = _elapsed_ms(started)
            return self._fail("degenerate")

        self.timings["recover_pose"] = _elapsed_ms(started)

        inliers = int(inliers)

        if inliers <= 0:
            return self._fail("degenerate")

        quality = inliers / max(len(good), 1)

        self.diagnostics.update({
            "inliers": inliers,
            "quality": round(float(quality), 4),
        })

        if inliers < MIN_INLIERS:
            return self._fail("few_matches")

        if quality < MIN_QUALITY and inliers < STRONG_INLIERS:
            return self._fail("few_matches")

        translation = np.asarray(translation, dtype=float).reshape(3)

        return {
            "R": np.asarray(rotation, dtype=float).tolist(),
            # Вектор единичной длины: направление движения, не метры.
            "t": translation.tolist(),
            "step_length": float(np.linalg.norm(translation)),
            "inliers": inliers,
            "quality": round(float(quality), 4),
            "blur_a": round(float(blur_a), 2),
            "blur_b": round(float(blur_b), 2),
            "features_a": features_a,
            "features_b": features_b,
            "matches": len(good),
            "units": "relative",
            "method": "orb-essential-usac",
            "skipped": False,
        }, None

    def _mask(self, image: np.ndarray) -> np.ndarray | None:
        """Построить маску динамики, если функция масок задана."""

        if self.dynamic_mask_fn is None:
            return None

        mask = self.dynamic_mask_fn(image)

        if mask is None:
            return None

        mask = np.asarray(mask)

        if mask.shape[:2] != image.shape[:2]:
            return None

        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8)

        return mask

    def _scaled_camera(self, scale: float) -> np.ndarray:
        """Пересчитать K под рабочую высоту кадра."""

        matrix = self.camera_matrix.copy()
        matrix[0, 0] *= scale
        matrix[1, 1] *= scale
        matrix[0, 2] *= scale
        matrix[1, 2] *= scale
        return matrix

    def _fail(
        self,
        reason: str,
    ) -> tuple[None, str]:
        """Запомнить причину отказа и вернуть пустой результат."""

        self.last_reason = reason
        self.diagnostics["reason"] = reason
        return None, reason


def _match(
    matcher: cv2.BFMatcher,
    descriptors_a: np.ndarray,
    descriptors_b: np.ndarray,
    ratio: float,
) -> list:
    """KNN-сопоставление с ratio test."""

    pairs = matcher.knnMatch(
        descriptors_a,
        descriptors_b,
        k=2,
    )

    good = []

    for pair in pairs:
        if len(pair) < 2:
            continue

        first, second = pair

        if first.distance < ratio * second.distance:
            good.append(first)

    return good


def _equalize(gray: np.ndarray) -> np.ndarray:
    """Выровнять локальный контраст через CLAHE."""

    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8),
    )

    return clahe.apply(gray)


def _read_image(image_path: Path) -> np.ndarray:
    """Прочитать изображение с поддержкой кириллицы в пути."""

    data = np.fromfile(str(image_path), dtype=np.uint8)

    if not data.size:
        raise ValueError(f"Пустой файл изображения: {image_path}")

    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(
            f"Не удалось прочитать изображение: {image_path}"
        )

    return image


def _prepare_pair(
    image_a: np.ndarray,
    image_b: np.ndarray,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    float,
]:
    """Привести кадры к одной высоте и вернуть цвета, серые и масштаб."""

    height_a = image_a.shape[0]
    scale = TARGET_HEIGHT / max(height_a, 1)

    color_a = _resize_to_height(image_a)
    color_b = _resize_to_height(image_b)

    gray_a = cv2.cvtColor(color_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(color_b, cv2.COLOR_BGR2GRAY)

    return color_a, color_b, gray_a, gray_b, scale


def _resize_to_height(image: np.ndarray) -> np.ndarray:
    """Изменить размер кадра так, чтобы высота стала TARGET_HEIGHT."""

    height, width = image.shape[:2]

    if height == TARGET_HEIGHT:
        return image

    scale = TARGET_HEIGHT / max(height, 1)
    new_width = max(1, int(round(width * scale)))

    interpolation = (
        cv2.INTER_AREA
        if scale < 1.0
        else cv2.INTER_LINEAR
    )

    return cv2.resize(
        image,
        (new_width, TARGET_HEIGHT),
        interpolation=interpolation,
    )


def _blur_score(gray: np.ndarray) -> float:
    """Дисперсия лапласиана: чем меньше, тем сильнее размытие."""

    return float(
        cv2.Laplacian(gray, cv2.CV_64F).var()
    )


def _single_matrix(essential) -> np.ndarray | None:
    """Привести ответ findEssentialMat к одной матрице 3×3."""

    if essential is None:
        return None

    matrix = np.asarray(essential, dtype=float)

    if matrix.shape == (3, 3):
        return matrix

    if matrix.ndim == 3 and matrix.shape[:2] == (3, 3):
        return matrix[:, :, 0]

    if matrix.size >= 9:
        return matrix.reshape(-1)[:9].reshape(3, 3)

    return None


def _elapsed_ms(started: float) -> int:
    """Перевести прошедшее время в целые миллисекунды."""

    return int(round((time.perf_counter() - started) * 1000))
