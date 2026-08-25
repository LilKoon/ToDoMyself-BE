import os
import uvicorn

if __name__ == "__main__":
    # Get port dynamically from Railway environment (falls back to 8000)
    port = int(os.getenv("PORT", 8000))
    print(f"Starting server on port {port}...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
