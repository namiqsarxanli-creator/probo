"""Original simulation, with its original SQLite data. Run separately on port 8811."""
import os
from app.server import serve

if __name__ == '__main__':
    os.environ.setdefault('PORT', '8811')
    serve()
