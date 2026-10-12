# How to Run NetChaos

There are two ways to run the NetChaos project: using Docker (Recommended) or running the backend and frontend separately.

## Method 1: Using Docker (Recommended)

This is the easiest method as it automatically spins up the MongoDB database, the FastAPI backend, and the React frontend.

```powershell
# From the netchaos-final directory:
docker compose up --build -d
```
* **Frontend Dashboard:** http://localhost:3001
* **Backend API Docs:** http://localhost:8001/docs


## Method 2: Running Manually (Without Docker)

If you prefer to run the components individually without Docker, you will need to have a MongoDB instance running on `localhost:27017` first.

**1. Start the Backend (FastAPI)**
Open a new terminal and run:
```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8001 --reload
```

**2. Start the Frontend (React/Vite)**
Open a second terminal and run:
```powershell
cd frontend
npm install
npm run dev
```
* **Frontend Dashboard:** http://localhost:5173
* **Backend API Docs:** http://localhost:8001/docs
