from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class RecheckMeasurement(Base):
    __tablename__ = 'recheck_measurements'

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('analysis_runs.id'), index=True)
    scan_id: Mapped[str] = mapped_column(String(64))
    angle_deg: Mapped[float] = mapped_column()
    measured_mm: Mapped[float] = mapped_column()
    created_by: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    created_at: Mapped[str] = mapped_column(String(32))
