"""
Pytest configuration file for PayvoraX test suite.
Ensures proper model loading and database fixtures for all tests.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base

# Import all models to ensure they are registered with SQLAlchemy
# This prevents "failed to locate a name" errors with relationships
from app.auth.models import User
from app.pix.models import PixTransaction
from app.boleto.models import BoletoTransaction
from app.parcelamento.models import InstallmentSimulation
from app.cards.models import CreditCard


# In-memory database for tests
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db():
    """
    Creates an in-memory database for each test function.
    Automatically tears down after test completes.
    """
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
