import Button from "../../ui/Button.jsx";




export default function UploadActions({
    uploading,
    hasFile,
}) {
    return (
        <div className="form-actions">
            <Button
                variant="primary"
                type="submit"
                disabled={uploading || !hasFile}
            >
                {uploading
                    ? "Загружаю…"
                    : "Загрузить и проанализировать"}
            </Button>
        </div>
    );
}