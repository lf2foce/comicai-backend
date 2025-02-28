import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine

# ✅ Load environment variables
load_dotenv()

# ✅ Get database URL from .env
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"DATABASE_URL: {DATABASE_URL}")  # ✅ Debugging line
if DATABASE_URL is None:
    raise ValueError("❌ ERROR: DATABASE_URL is not set. Make sure to export it.")

# ✅ Create Database Engine
engine = create_engine(DATABASE_URL, echo=False)  # ✅ echo=True for debugging

# ✅ Function to Initialize DB
def init_db():
    SQLModel.metadata.create_all(engine)

# ✅ Dependency to Get a Database Session
def get_session():
    with Session(engine) as session:
        yield session
