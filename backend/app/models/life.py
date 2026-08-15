from datetime import date

from sqlalchemy import Date, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class LifeProfile(UUIDMixin, TimestampMixin, Base):
    """人生倒數的基準資料：生日與預期壽命。

    單人自用，全表語意上只有一列——寫入一律走 services.life.upsert_profile，
    它會更新既有那列而非新增，避免出現「哪一列才算數」的歧義。
    """

    __tablename__ = "life_profile"

    birthday: Mapped[date] = mapped_column(Date)
    life_expectancy: Mapped[int] = mapped_column(Integer, default=80)
