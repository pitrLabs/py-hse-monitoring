from fastapi import FastAPI
from app.database import init_db
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, users, roles, video_sources

app = FastAPI(title="HSE Object Detection Monitoring",
              description="User Management with Authentication, Roles, and Permissions",
              version="1.0.0")

app.add_middleware(CORSMiddleware,
                   allow_credentials=True,
                   allow_origins=["*"],
                   allow_methods=["*"],
                   allow_headers=["*"])

@app.on_event("startup")
def startup_event():
    init_db()

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(video_sources.router)

@app.get("/")
def root():
    return {
        "message": "HSE Monitoring API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
