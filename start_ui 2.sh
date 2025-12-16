#!/bin/bash
# Start script for the AP Agent UI

set -e

cd "$(dirname "$0")"

echo "Starting AP Agent UI..."
echo ""

# Check backend env
if [ ! -d "venv" ]; then
  echo "Error: venv not found. Please create and install backend deps first."
  exit 1
fi

source venv/bin/activate

echo "Ensuring backend deps..."
pip install -q fastapi "uvicorn[standard]" pandas 2>/dev/null || true

echo "Starting backend API on http://localhost:8000 ..."
PYTHONPATH=. uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > api.log 2>&1 &
BACKEND_PID=$!

sleep 2

echo "Installing frontend deps if needed..."
cd frontend
npm install >/dev/null 2>&1 || true

echo "Starting frontend on http://localhost:3000 ..."
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!

echo ""
echo "✅ UI is running!"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:8000"
echo ""
echo "Logs: api.log, frontend.log"
echo "Use 'kill $BACKEND_PID $FRONTEND_PID' to stop."

wait
#!/bin/bash
# Start script for the AP Agent UI

echo "Starting AP Agent UI..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Please run 'poetry install' first."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Install backend dependencies if needed
echo "Checking backend dependencies..."
pip install -q fastapi uvicorn[standard] 2>/dev/null || echo "Dependencies already installed"

# Start backend in background
echo "Starting backend API on http://localhost:8000..."
python api/main.py &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Check if frontend dependencies are installed
if [ ! -d "frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd frontend
    npm install
    cd ..
fi

# Start frontend
echo "Starting frontend on http://localhost:3000..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ UI is running!"
echo "   Frontend: http://localhost:3000"
echo "   Backend API: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for user interrupt
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait

