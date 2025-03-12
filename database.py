import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.exc import OperationalError
import time
import logging

# ✅ Load environment variables
load_dotenv()

# ✅ Get database URL from .env
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"DATABASE_URL: {DATABASE_URL}")  # ✅ Debugging line
if DATABASE_URL is None:
    raise ValueError("❌ ERROR: DATABASE_URL is not set. Make sure to export it.")

# ✅ Create Database Engine
engine = create_engine(DATABASE_URL, echo=False,
    pool_size=10,         # ✅ Max connections in the pool
    max_overflow=20,      # ✅ Allow extra connections beyond pool_size
    pool_recycle=300,     # ✅ Refresh connections every 5 minutes
    pool_pre_ping=True,   # ✅ Check if the connection is still alive before using)  # ✅ echo=True for debugging
)
# ✅ Function to Initialize DB
def init_db():
    SQLModel.metadata.create_all(engine)

# ✅ Dependency to Get a Database Session
def get_session():
    with Session(engine) as session:
        yield session

# ✅ Commit with Automatic Retry (Handles Intermittent Errors)
# def commit_with_retry(session, retries=3):
#     """Commit transaction with retries to handle transient failures."""
#     for attempt in range(retries):
#         try:
#             session.commit()
#             return
#         except OperationalError as e:
#             session.rollback()
#             print(f"❌ Commit failed (attempt {attempt + 1}): {e}")
#             if attempt == retries - 1:
#                 raise
#             time.sleep(1)  # ✅ Small delay before retrying

# ✅ Commit with Automatic Retry (Handles Intermittent Errors)
def commit_with_retry(session, retries=5, base_delay=1, max_delay=30):
    """Commit transaction with retries and exponential backoff."""
    for attempt in range(retries):
        try:
            session.commit()
            logging.info("✅ Commit successful.")
            return
        except OperationalError as e:
            session.rollback()
            logging.error(f"❌ Commit failed (attempt {attempt + 1}/{retries}): {e}")
            if attempt == retries - 1:
                logging.error("❌ Maximum retries reached. Commit failed.")
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            logging.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
        except Exception as e:
            session.rollback()
            logging.error(f"An unexpected error occured during commit: {e}")
            raise #re-raise the error.