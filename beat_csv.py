"""CSV import/export for user-owned Beats."""
import csv
import io
from datetime import datetime
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

HEADERS = ["Date", "Time", "Beat", "Rhythmos", "Accent"]
MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000

def register_beat_data(app, db, SumEntry, LifeArea):
    bp = Blueprint("beat_data", __name__, url_prefix="/settings/beat-data")

    def serializer():
        return URLSafeTimedSerializer(current_app.secret_key, salt="beat-csv-import-v1")

    @bp.get("/")
    @login_required
    def index():
        return render_template("beat_data.html")

    @bp.get("/template.csv")
    @login_required
    def template():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        writer.writerow(["2026-10-25", "14:30", "Played outside with my son", "Family", "Yes"])
        return Response("\ufeff" + output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=beats-template.csv"})

    @bp.get("/export.csv")
    @login_required
    def export():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        entries = SumEntry.query.filter_by(user_id=current_user.id).order_by(SumEntry.occurred_on, SumEntry.id).all()
        for entry in entries:
            # CSV spreadsheet safety: prevent cells from becoming executable formulas.
            def safe(value):
                value = str(value or "")
                return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
            writer.writerow([entry.occurred_on.isoformat(), "",
                             safe(entry.description), safe(entry.life_area.name if entry.life_area else ""),
                             "Yes" if entry.accented else "No"])
        return Response("\ufeff" + output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=beats-export.csv"})

    @bp.post("/preview")
    @login_required
    def preview():
        file = request.files.get("file")
        if not file or not file.filename.lower().endswith(".csv"):
            flash("Choose a CSV file.", "error")
            return redirect(url_for("beat_data.index"))
        data = file.stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            flash("CSV must be smaller than 1 MB.", "error")
            return redirect(url_for("beat_data.index"))
        try:
            reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
            if reader.fieldnames != HEADERS:
                raise ValueError("Columns must be: " + ", ".join(HEADERS))
            rows = list(reader)
            if not rows or len(rows) > MAX_ROWS:
                raise ValueError("Provide between 1 and 1,000 Beats.")
            areas = {a.name.casefold(): a for a in LifeArea.query.filter_by(user_id=current_user.id).all()}
            existing = {(e.occurred_on.isoformat(), e.description.strip().casefold())
                        for e in SumEntry.query.filter_by(user_id=current_user.id).all()}
            seen = set()
            parsed, errors, new_areas = [], [], set()
            for number, row in enumerate(rows, 2):
                try:
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError("Incorrect number of columns")
                    day = datetime.strptime(row["Date"].strip(), "%Y-%m-%d").date()
                    time = row["Time"].strip()
                    if time:
                        datetime.strptime(time, "%H:%M")
                    beat = row["Beat"].strip()
                    if not beat or len(beat) > 5000:
                        raise ValueError("Beat must contain 1–5,000 characters")
                    area = row["Rhythmos"].strip()
                    if len(area) > 120:
                        raise ValueError("Rhythmos name is too long")
                    accent = row["Accent"].strip().casefold()
                    if accent not in ("", "yes", "no"):
                        raise ValueError("Accent must be Yes or No")
                    key = (day.isoformat(), beat.casefold())
                    if key in existing or key in seen:
                        raise ValueError("Potential duplicate Beat on this date")
                    seen.add(key)
                    if area and area.casefold() not in areas:
                        new_areas.add(area)
                    parsed.append({"date": day.isoformat(), "time": time, "beat": beat,
                                   "area": area, "accent": accent == "yes"})
                except ValueError as exc:
                    errors.append(f"Row {number}: {exc}")
            token = serializer().dumps({"user": current_user.id, "rows": parsed}) if not errors else None
            return render_template("beat_data.html", rows=parsed, errors=errors,
                                   new_areas=sorted(new_areas), token=token)
        except (UnicodeError, csv.Error, ValueError) as exc:
            flash(f"Unable to read CSV: {exc}", "error")
            return redirect(url_for("beat_data.index"))

    @bp.post("/confirm")
    @login_required
    def confirm():
        try:
            payload = serializer().loads(request.form.get("token", ""), max_age=1800)
        except (BadSignature, SignatureExpired):
            abort(400, "Import preview expired. Upload your CSV again.")
        if payload.get("user") != current_user.id:
            abort(403)
        rows = payload.get("rows", [])
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
            abort(400)
        create_areas = request.form.get("create_areas") == "yes"
        areas = {a.name.casefold(): a for a in LifeArea.query.filter_by(user_id=current_user.id).all()}
        existing = {(e.occurred_on.isoformat(), e.description.strip().casefold())
                    for e in SumEntry.query.filter_by(user_id=current_user.id).all()}
        try:
            for row in rows:
                day = datetime.strptime(row["date"], "%Y-%m-%d").date()
                beat = row["beat"]
                if (day.isoformat(), beat.casefold()) in existing:
                    raise ValueError("One or more Beats already exist. Upload again to review.")
                existing.add((day.isoformat(), beat.casefold()))
                name = row["area"]
                area = areas.get(name.casefold()) if name else None
                if name and area is None and create_areas:
                    area = LifeArea(user_id=current_user.id, name=name, active=True,
                                    sort_order=len(areas))
                    db.session.add(area)
                    db.session.flush()
                    areas[name.casefold()] = area
                logged_at = datetime.combine(day, datetime.strptime(row["time"], "%H:%M").time()) if row["time"] else datetime.utcnow()
                db.session.add(SumEntry(user_id=current_user.id, life_area_id=area.id if area else None,
                                        description=beat, value=1, accented=bool(row["accent"]),
                                        occurred_on=day, logged_at=logged_at))
            db.session.commit()
        except (ValueError, KeyError, TypeError):
            db.session.rollback()
            flash("Import could not be completed. Upload the CSV again.", "error")
            return redirect(url_for("beat_data.index"))
        flash(f"Imported {len(rows)} Beats.", "success")
        return redirect(url_for("beat_data.index"))

    app.register_blueprint(bp)
