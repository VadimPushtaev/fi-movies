from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class City(Base, TimestampMixin):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    theaters: Mapped[list["Theater"]] = relationship(back_populates="city")


class Theater(Base, TimestampMixin):
    __tablename__ = "theaters"
    __table_args__ = (UniqueConstraint("source", "source_theater_id", name="uq_theaters_source_theater"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_theater_id: Mapped[str] = mapped_column(String(120), nullable=False)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    webpage_url: Mapped[str | None] = mapped_column(Text)
    phone_number: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(250))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    api_id: Mapped[str | None] = mapped_column(String(80))

    city: Mapped[City] = relationship(back_populates="theaters")
    showtimes: Mapped[list["Showtime"]] = relationship(back_populates="theater")


class Movie(Base, TimestampMixin):
    __tablename__ = "movies"
    __table_args__ = (UniqueConstraint("source", "source_movie_id", name="uq_movies_source_movie"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_movie_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source_internal_id: Mapped[str | None] = mapped_column(String(120))
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    slug: Mapped[str] = mapped_column(String(240), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(500))
    swedish_title: Mapped[str | None] = mapped_column(String(500))
    poster_url: Mapped[str | None] = mapped_column(Text)
    trailer_url: Mapped[str | None] = mapped_column(Text)
    age_limit: Mapped[str | None] = mapped_column(String(40))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    genres: Mapped[str | None] = mapped_column(Text)
    distributor: Mapped[str | None] = mapped_column(String(250))
    premiere_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    director: Mapped[str | None] = mapped_column(Text)
    script: Mapped[str | None] = mapped_column(Text)
    actors: Mapped[str | None] = mapped_column(Text)
    raw_url: Mapped[str | None] = mapped_column(Text)

    showtimes: Mapped[list["Showtime"]] = relationship(back_populates="movie")


class Showtime(Base, TimestampMixin):
    __tablename__ = "showtimes"
    __table_args__ = (UniqueConstraint("source_key", name="uq_showtimes_source_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_show_id: Mapped[str | None] = mapped_column(String(180))
    source_raw_id: Mapped[str | None] = mapped_column(String(180))
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id"), nullable=False)
    theater_id: Mapped[int] = mapped_column(ForeignKey("theaters.id"), nullable=False)
    auditorium: Mapped[str | None] = mapped_column(String(250))
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    order_page_url: Mapped[str | None] = mapped_column(Text)

    movie: Mapped[Movie] = relationship(back_populates="showtimes")
    theater: Mapped[Theater] = relationship(back_populates="showtimes")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    message: Mapped[str | None] = mapped_column(Text)
    movies_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    theaters_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    showtimes_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
