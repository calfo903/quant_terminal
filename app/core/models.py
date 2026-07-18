"""ORM models for the relational stores (TimescaleDB / Postgres).



These register tables on `Base.metadata` so `app.db_init` can create them.

Keep this module import-light: it must not trigger network/IO at import time.

"""

from sqlalchemy import (

    Boolean,

    Column,

    DateTime,

    Float,

    Integer,

    String,

)

from sqlalchemy.dialects.postgresql import JSONB



from app.core.database import Base





class Candle(Base):

    __tablename__ = "candles"

    instrument = Column(String, primary_key=True)

    timeframe = Column(String, primary_key=True)

    time = Column(DateTime(timezone=True), primary_key=True)

    open = Column(Float)

    high = Column(Float)

    low = Column(Float)

    close = Column(Float)

    volume = Column(Float)





class Tick(Base):

    __tablename__ = "ticks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    instrument = Column(String, index=True)

    time = Column(DateTime(timezone=True), index=True)

    price = Column(Float)

    quantity = Column(Float)

    is_buy = Column(Boolean)

    received_at = Column(DateTime(timezone=True), index=True)





class ImageAnalysis(Base):

    __tablename__ = "image_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)

    created_at = Column(DateTime(timezone=True))

    model_version = Column(String)

    image_size = Column(Integer)

    analysis_result = Column(JSONB)





class Prediction(Base):

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    created_at = Column(DateTime(timezone=True), index=True)

    instrument = Column(String, index=True)

    signal = Column(String)

    confidence = Column(Float)

    model_version = Column(String)





class Trade(Base):

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)

    created_at = Column(DateTime(timezone=True), index=True)

    instrument = Column(String, index=True)

    side = Column(String)

    size = Column(Float)

    price = Column(Float)

    pnl = Column(Float, nullable=True)
