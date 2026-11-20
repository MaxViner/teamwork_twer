
## Запуск

```bash
pip install -r requirements.txt
# требуются: ffmpeg и ffprobe в PATH
# exiftool не обязателен: метаданные MP4/MOV читаются без него

запуск сервера -
 uvicorn app.server.server:appServer --reload
```
запуск интерфеса - npm run dev

