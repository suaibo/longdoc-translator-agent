from fastapi import FastAPI


app = FastAPI(title="LongDoc Translator Agent", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "status": "UP",
            "service": "longdoc-translator-agent",
        },
    }
