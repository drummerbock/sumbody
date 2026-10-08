import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import case, func
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "login"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False, default="Becoming the Heartbeat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    onboarding_complete = db.Column(db.Boolean, default=False, nullable=False)
    silk_visible_fields = db.Column(db.String(160), nullable=False, default="")

class LifeArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SumEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    life_area_id = db.Column(db.Integer, db.ForeignKey("life_area.id"), nullable=True, index=True)
    description = db.Column(db.Text, nullable=False)
    value = db.Column(db.Integer, nullable=False)
    communicated = db.Column(db.Boolean, nullable=True)
    occurred_on = db.Column(db.Date, nullable=False, index=True)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    legacy_timestamp = db.Column(db.String(80), nullable=True)
    archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
    accented = db.Column(db.Boolean, default=False, nullable=False, index=True)
    life_area = db.relationship("LifeArea")

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    life_area_id = db.Column(db.Integer, db.ForeignKey("life_area.id"), nullable=False, index=True)
    intention = db.Column(db.String(240), nullable=False)
    target = db.Column(db.String(120), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    life_area = db.relationship("LifeArea")

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required.")

    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///" + str(Path(app.instance_path) / "sumbody.db")
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SUPER_ADMIN_EMAIL"] = os.environ.get("SUPER_ADMIN_EMAIL", "").strip().lower()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = True

    try:
        app_tz = ZoneInfo(os.environ.get("APP_TIMEZONE", "America/New_York"))
    except Exception as exc:
        raise RuntimeError("APP_TIMEZONE must be a valid IANA timezone.") from exc

    def local_today():
        return datetime.now(app_tz).date()

    def current_user_is_super_admin():
        admin_email = app.config["SUPER_ADMIN_EMAIL"]
        return bool(
            current_user.is_authenticated
            and admin_email
            and current_user.email.lower() == admin_email
        )

    def require_super_admin():
        if not current_user_is_super_admin():
            abort(403)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    with app.app_context():
        if db.engine.url.get_backend_name() == "sqlite":
            from sqlite_migrations import migrate_nullable_beat_area
            database_path = db.engine.url.database
            if database_path and database_path != ":memory:":
                migrate_nullable_beat_area(database_path)
        db.create_all()
        # Lightweight SQLite migrations for existing installations.
        columns = {row[1] for row in db.session.execute(db.text("PRAGMA table_info(sum_entry)"))}
        if "archived" not in columns:
            db.session.execute(db.text("ALTER TABLE sum_entry ADD COLUMN archived BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        if "accented" not in columns:
            db.session.execute(db.text("ALTER TABLE sum_entry ADD COLUMN accented BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
        life_area_columns = {row[1] for row in db.session.execute(db.text("PRAGMA table_info(life_area)"))}
        if "sort_order" not in life_area_columns:
            db.session.execute(db.text("ALTER TABLE life_area ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
            # Preserve each user's current alphabetical presentation as the initial custom order.
            user_ids = [row[0] for row in db.session.execute(db.text("SELECT DISTINCT user_id FROM life_area"))]
            for user_id in user_ids:
                area_ids = [row[0] for row in db.session.execute(
                    db.text("SELECT id FROM life_area WHERE user_id = :uid ORDER BY name COLLATE NOCASE, id"),
                    {"uid": user_id},
                )]
                for position, area_id in enumerate(area_ids):
                    db.session.execute(
                        db.text("UPDATE life_area SET sort_order = :position WHERE id = :area_id"),
                        {"position": position, "area_id": area_id},
                    )
            db.session.commit()
        user_columns = {row[1] for row in db.session.execute(db.text("PRAGMA table_info(user)"))}
        if "silk_visible_fields" not in user_columns:
            db.session.execute(db.text("ALTER TABLE user ADD COLUMN silk_visible_fields VARCHAR(160) NOT NULL DEFAULT ''"))
            db.session.commit()
        if "onboarding_complete" not in user_columns:
            db.session.execute(db.text("ALTER TABLE user ADD COLUMN onboarding_complete BOOLEAN NOT NULL DEFAULT 1"))
            db.session.commit()

    @app.after_request
    def prevent_stale_html(response):
        if response.content_type and response.content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def globals():
        context = {"today": local_today(), "composer_areas": [], "is_super_admin": current_user_is_super_admin(), "silk_visible_fields": []}
        if current_user.is_authenticated:
            context["silk_visible_fields"] = [x for x in (current_user.silk_visible_fields or "").split(",") if x in ("area", "accent", "date", "shared")]
            context["composer_areas"] = LifeArea.query.filter_by(
                user_id=current_user.id, active=True
            ).order_by(LifeArea.sort_order, LifeArea.name).all()
        return context

    @app.route("/")
    @login_required
    def home():
        today = local_today()
        yesterday = today - timedelta(days=1)

        def totals(day):
            q = SumEntry.query.filter_by(user_id=current_user.id, occurred_on=day, archived=False)
            return q.count(), q.filter_by(accented=True).count()

        today_count, today_accents = totals(today)
        yesterday_count, yesterday_accents = totals(yesterday)
        recent = SumEntry.query.filter_by(
            user_id=current_user.id, occurred_on=today
        ).order_by(SumEntry.archived.asc(), SumEntry.logged_at.desc()).all()
        return render_template(
            "home.html",
            today_count=today_count,
            today_accents=today_accents,
            yesterday_count=yesterday_count,
            yesterday_accents=yesterday_accents,
            recent=recent,
        )

    @app.post("/silk/preferences")
    @login_required
    def silk_preferences():
        allowed = {"area", "accent", "date", "shared"}
        payload = request.get_json(silent=True) or {}
        fields = payload.get("fields")
        if not isinstance(fields, list) or len(fields) > 4 or any(not isinstance(x, str) or x not in allowed for x in fields):
            return jsonify(ok=False, error="Invalid field preferences."), 400
        current_user.silk_visible_fields = ",".join(dict.fromkeys(fields))
        db.session.commit()
        return jsonify(ok=True, fields=list(dict.fromkeys(fields)))

    @app.route("/add", methods=["GET", "POST"])
    @login_required
    def add_sum():
        areas = LifeArea.query.filter_by(
            user_id=current_user.id, active=True
        ).order_by(LifeArea.sort_order, LifeArea.name).all()
        wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        def invalid(message):
            if wants_json:
                return jsonify(ok=False, error=message), 400
            flash(message, "error")
            return render_template("add.html", areas=areas)

        if request.method == "POST":
            description = request.form.get("description", "").strip()
            raw_area = request.form.get("life_area_id", "").strip()
            area = None
            if raw_area:
                try:
                    area_id = int(raw_area)
                except ValueError:
                    return invalid("Choose a valid Life Area or leave it blank.")
                area = LifeArea.query.filter_by(id=area_id, user_id=current_user.id, active=True).first()
                if not area:
                    return invalid("Choose a valid Life Area or leave it blank.")
            try:
                occurred_on = datetime.strptime(request.form.get("occurred_on", ""), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return invalid("Choose a valid date.")
            if not description:
                return invalid("Write something to remember.")

            comm = request.form.get("communicated")
            accented = request.form.get("accented") == "yes"
            entry = SumEntry(
                user_id=current_user.id,
                life_area_id=area.id if area else None,
                description=description,
                value=1,
                accented=accented,
                communicated=True if comm == "yes" else False if comm == "no" else None,
                occurred_on=occurred_on,
            )
            db.session.add(entry)
            db.session.commit()

            if wants_json:
                today = local_today()
                today_count = SumEntry.query.filter_by(
                    user_id=current_user.id, occurred_on=today, archived=False
                ).count()
                today_accents = SumEntry.query.filter_by(
                    user_id=current_user.id, occurred_on=today, archived=False, accented=True
                ).count()
                return jsonify(
                    ok=True,
                    entry={
                        "id": entry.id,
                        "description": entry.description,
                        "life_area": area.name if area else "",
                        "life_area_id": area.id if area else None,
                        "accented": entry.accented,
                        "occurred_on": entry.occurred_on.isoformat(),
                    },
                    today_count=today_count,
                    today_accents=today_accents,
                )

            flash("Beat added.", "success")
            return redirect(url_for("home"))
        return render_template("add.html", areas=areas)

    @app.route("/history")
    @login_required
    def history():
        archived_view = request.args.get("archived") == "1"
        q = SumEntry.query.filter_by(user_id=current_user.id, archived=archived_view)
        search = request.args.get("q", "").strip()
        area = request.args.get("area", type=int)
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        if search:
            q = q.filter(SumEntry.description.ilike(f"%{search}%"))
        if area:
            q = q.filter(SumEntry.life_area_id == area)
        if start:
            try:
                q = q.filter(SumEntry.occurred_on >= datetime.strptime(start, "%Y-%m-%d").date())
            except ValueError:
                pass
        if end:
            try:
                q = q.filter(SumEntry.occurred_on <= datetime.strptime(end, "%Y-%m-%d").date())
            except ValueError:
                pass

        total_count = q.count()
        accent_count = q.filter(SumEntry.accented.is_(True)).count()
        entries = q.order_by(
            SumEntry.occurred_on.desc(), SumEntry.logged_at.desc()
        ).limit(500).all()
        areas = LifeArea.query.filter_by(
            user_id=current_user.id
        ).order_by(LifeArea.sort_order, LifeArea.name).all()

        insight_entries = SumEntry.query.filter_by(
            user_id=current_user.id, archived=False
        ).all()
        insight_total_count = len(insight_entries)
        insight_accent_count = sum(1 for e in insight_entries if e.accented)
        by_area = db.session.query(
            LifeArea.name,
            func.count(SumEntry.id),
            func.sum(case((SumEntry.accented.is_(True), 1), else_=0)),
        ).join(SumEntry).filter(
            SumEntry.user_id == current_user.id,
            SumEntry.archived.is_(False),
        ).group_by(LifeArea.id).order_by(func.count(SumEntry.id).desc()).all()
        unassigned_count = SumEntry.query.filter_by(user_id=current_user.id, archived=False, life_area_id=None).count()
        days = db.session.query(
            SumEntry.occurred_on,
            func.count(SumEntry.id),
            func.sum(case((SumEntry.accented.is_(True), 1), else_=0)),
        ).filter_by(
            user_id=current_user.id, archived=False
        ).group_by(SumEntry.occurred_on).all()
        most_active = max(days, key=lambda x: x[1]) if days else None
        most_accented = max(days, key=lambda x: x[2] or 0) if days else None
        # Audify visualizations are strictly descriptive: only user-recorded Beats.
        # Build the recent 7-day timeline, including days with zero records, without
        # implying that an unrecorded day was unproductive or intentionally silent.
        timeline = []
        for offset in range(6, -1, -1):
            day = local_today() - timedelta(days=offset)
            day_entries = [entry for entry in insight_entries if entry.occurred_on == day]
            timeline.append({
                "label": day.strftime("%a"),
                "date": day.isoformat(),
                "count": len(day_entries),
                "accents": sum(1 for entry in day_entries if entry.accented),
            })
        insight_area_rows = [
            {"name": name, "count": count, "accents": accents or 0}
            for name, count, accents in by_area
        ]
        if unassigned_count:
            insight_area_rows.append({"name": "Not categorized", "count": unassigned_count, "accents": sum(1 for entry in insight_entries if entry.life_area_id is None and entry.accented)})
        insight_area_rows.sort(key=lambda row: (-row["count"], row["name"]))
        max_area_count = max((row["count"] for row in insight_area_rows), default=0)
        max_day_count = max((day["count"] for day in timeline), default=0)
        communicated = sum(1 for e in insight_entries if e.communicated is True)
        comm_known = sum(1 for e in insight_entries if e.communicated is not None)

        return render_template(
            "history.html",
            entries=entries,
            total_count=total_count,
            accent_count=accent_count,
            areas=areas,
            archived_view=archived_view,
            insight_total_count=insight_total_count,
            insight_accent_count=insight_accent_count,
            by_area=by_area,
            insight_area_rows=insight_area_rows,
            max_area_count=max_area_count,
            timeline=timeline,
            max_day_count=max_day_count,
            unassigned_count=unassigned_count,
            most_active=most_active,
            most_accented=most_accented,
            communicated=communicated,
            comm_known=comm_known,
        )

    @app.route("/insights")
    @login_required
    def insights():
        return redirect(url_for("history"))

    @app.route("/areas", methods=["GET", "POST"])
    @login_required
    def areas():
        # Keep old links and POST forms working, but expose one unified page.
        if request.method == "POST":
            return goals()
        return redirect(url_for("goals"))

    @app.post("/areas/<int:area_id>/toggle")
    @login_required
    def toggle_area(area_id):
        area = LifeArea.query.filter_by(
            id=area_id, user_id=current_user.id
        ).first_or_404()
        area.active = not area.active
        db.session.commit()
        return redirect(url_for("goals"))

    @app.post("/areas/reorder")
    @login_required
    def reorder_areas():
        ids = request.get_json(silent=True, force=False) or {}
        ids = ids.get("ids", [])
        if not isinstance(ids, list):
            return jsonify(ok=False), 400
        active = LifeArea.query.filter_by(user_id=current_user.id, active=True).all()
        active_ids = {a.id for a in active}
        try:
            ordered_ids = [int(area_id) for area_id in ids]
        except (TypeError, ValueError):
            return jsonify(ok=False), 400
        if set(ordered_ids) != active_ids or len(ordered_ids) != len(active_ids):
            return jsonify(ok=False), 400
        by_id = {a.id: a for a in active}
        for position, area_id in enumerate(ordered_ids):
            by_id[area_id].sort_order = position
        db.session.commit()
        return jsonify(ok=True)

    @app.post("/areas/<int:area_id>/move/<direction>")
    @login_required
    def move_area(area_id, direction):
        if direction not in {"up", "down"}:
            abort(400)
        area = LifeArea.query.filter_by(id=area_id, user_id=current_user.id).first_or_404()
        ordered = LifeArea.query.filter_by(user_id=current_user.id, active=area.active).order_by(
            LifeArea.sort_order, LifeArea.name
        ).all()
        index = next((i for i, item in enumerate(ordered) if item.id == area.id), None)
        target_index = index - 1 if direction == "up" else index + 1
        if index is not None and 0 <= target_index < len(ordered):
            other = ordered[target_index]
            area.sort_order, other.sort_order = other.sort_order, area.sort_order
            db.session.commit()
        return redirect(url_for("areas"))

    @app.post("/sum/<int:entry_id>/toggle-archive")
    @login_required
    def toggle_sum_archive(entry_id):
        entry = SumEntry.query.filter_by(
            id=entry_id, user_id=current_user.id
        ).first_or_404()
        entry.archived = not entry.archived
        db.session.commit()
        flash("Beat restored." if not entry.archived else "Beat archived.", "success")
        return redirect(request.referrer or url_for("history"))

    @app.post("/sum/<int:entry_id>/area")
    @login_required
    def set_sum_area(entry_id):
        entry = SumEntry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
        raw = request.form.get("life_area_id", "").strip()
        area = None
        if raw:
            try:
                area_id = int(raw)
            except ValueError:
                return jsonify(ok=False, error="Invalid Life Area."), 400
            area = LifeArea.query.filter_by(id=area_id, user_id=current_user.id).first()
            if not area:
                return jsonify(ok=False, error="Invalid Life Area."), 400
        entry.life_area_id = area.id if area else None
        db.session.commit()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=True, life_area=area.name if area else "", life_area_id=entry.life_area_id)
        return redirect(request.referrer or url_for("history"))

    @app.route("/sum/<int:entry_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_sum(entry_id):
        entry = SumEntry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
        areas = LifeArea.query.filter_by(user_id=current_user.id).order_by(LifeArea.sort_order, LifeArea.name).all()
        if request.method == "POST":
            description = request.form.get("description", "").strip()
            area_id = request.form.get("life_area_id", type=int)
            area = next((a for a in areas if a.id == area_id), None)
            try:
                occurred_on = datetime.strptime(request.form.get("occurred_on", ""), "%Y-%m-%d").date()
            except ValueError:
                occurred_on = None
            if not description or (area_id is not None and not area) or not occurred_on:
                flash("Please check the Beat details.", "error")
            else:
                entry.description = description
                entry.life_area_id = area.id if area else None
                entry.occurred_on = occurred_on
                entry.accented = request.form.get("accented") == "yes"
                entry.communicated = True if request.form.get("communicated") == "yes" else None
                db.session.commit()
                flash("Beat updated.", "success")
                return redirect(url_for("history") + "#beats")
        return render_template("edit_beat.html", entry=entry, areas=areas)

    @app.post("/sum/<int:entry_id>/toggle-accent")
    @login_required
    def toggle_sum_accent(entry_id):
        entry = SumEntry.query.filter_by(
            id=entry_id, user_id=current_user.id
        ).first_or_404()
        entry.accented = not entry.accented
        db.session.commit()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=True, accented=entry.accented)
        flash("Beat accented." if entry.accented else "Accent removed.", "success")
        return redirect(request.referrer or url_for("home"))

    @app.route("/goals", methods=["GET", "POST"])
    @login_required
    def goals():
        # Rhythmos are the existing LifeArea records: preserve Beat associations,
        # ordering and archives without a destructive database migration.
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if name and not LifeArea.query.filter(
                func.lower(LifeArea.name) == name.lower(),
                LifeArea.user_id == current_user.id,
            ).first():
                next_order = db.session.query(func.coalesce(func.max(LifeArea.sort_order), -1)).filter_by(
                    user_id=current_user.id
                ).scalar() + 1
                db.session.add(LifeArea(user_id=current_user.id, name=name, sort_order=next_order))
                db.session.commit()
                flash("Rhythmos added.", "success")
            elif not name:
                flash("Name your Rhythmos.", "error")
            else:
                flash("That Rhythmos already exists.", "error")
            return redirect(url_for("goals"))
        return render_template(
            "goals.html",
            areas=LifeArea.query.filter_by(user_id=current_user.id).order_by(
                LifeArea.active.desc(), LifeArea.sort_order, LifeArea.name
            ).all(),
            legacy_goals=Goal.query.filter_by(user_id=current_user.id).order_by(
                Goal.active.desc(), Goal.created_at.desc()
            ).all(),
        )

    @app.post("/goals/<int:goal_id>/toggle")
    @login_required
    def toggle_goal(goal_id):
        goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
        goal.active = not goal.active
        db.session.commit()
        return redirect(url_for("goals"))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if current_user.is_authenticated:
            return redirect(url_for("home"))
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if not name or not email:
                flash("Enter your name and email.", "error")
            elif len(password) < 10:
                flash("Use a password with at least 10 characters.", "error")
            elif password != confirm:
                flash("Passwords do not match.", "error")
            elif User.query.filter(func.lower(User.email) == email).first():
                flash("An account already exists for that email.", "error")
            else:
                user = User(name=name, email=email, password_hash=generate_password_hash(password), onboarding_complete=False)
                db.session.add(user)
                db.session.flush()
                for area_name in ["Family", "Friends", "Myself", "Work", "Other"]:
                    db.session.add(LifeArea(user_id=user.id, name=area_name))
                db.session.commit()
                login_user(user, remember=True)
                return redirect(url_for("onboarding"))
        return render_template("signup.html")

    @app.route("/onboarding", methods=["GET", "POST"])
    @login_required
    def onboarding():
        if request.method == "POST":
            current_user.onboarding_complete = True
            db.session.commit()
            return redirect(url_for("home"))
        return render_template("onboarding.html")

    @app.route("/musical-language")
    @login_required
    def musical_language():
        return render_template("musical_language.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("home"))
        if request.method == "POST":
            user = User.query.filter_by(
                email=request.form.get("email", "").strip().lower()
            ).first()
            if user and check_password_hash(
                user.password_hash, request.form.get("password", "")
            ):
                login_user(user, remember=True)
                if not user.onboarding_complete:
                    return redirect(url_for("onboarding"))
                return redirect(url_for("home"))
            flash("Email or password not recognized.", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/admin")
    @login_required
    def admin_dashboard():
        require_super_admin()

        users = User.query.order_by(User.created_at.desc()).all()
        user_rows = []
        for user in users:
            beat_count = SumEntry.query.filter_by(
                user_id=user.id, archived=False
            ).count()
            active_area_count = LifeArea.query.filter_by(
                user_id=user.id, active=True
            ).count()
            last_activity = db.session.query(
                func.max(SumEntry.logged_at)
            ).filter(SumEntry.user_id == user.id).scalar()
            user_rows.append({
                "user": user,
                "beat_count": beat_count,
                "active_area_count": active_area_count,
                "last_activity": last_activity,
            })

        return render_template(
            "admin.html",
            user_rows=user_rows,
            total_users=len(user_rows),
            total_beats=SumEntry.query.filter_by(archived=False).count(),
        )

    @app.route("/admin/users/<int:user_id>")
    @login_required
    def admin_user(user_id):
        require_super_admin()

        user = User.query.get_or_404(user_id)
        beat_count = SumEntry.query.filter_by(
            user_id=user.id, archived=False
        ).count()
        archived_beat_count = SumEntry.query.filter_by(
            user_id=user.id, archived=True
        ).count()
        accent_count = SumEntry.query.filter_by(
            user_id=user.id, archived=False, accented=True
        ).count()
        active_area_count = LifeArea.query.filter_by(
            user_id=user.id, active=True
        ).count()
        rhythmos_count = Goal.query.filter_by(
            user_id=user.id, active=True
        ).count()
        last_activity = db.session.query(
            func.max(SumEntry.logged_at)
        ).filter(SumEntry.user_id == user.id).scalar()

        return render_template(
            "admin_user.html",
            viewed_user=user,
            beat_count=beat_count,
            archived_beat_count=archived_beat_count,
            accent_count=accent_count,
            active_area_count=active_area_count,
            rhythmos_count=rhythmos_count,
            last_activity=last_activity,
        )

    @app.cli.command("create-user")
    def create_user():
        import getpass
        email = input("Email: ").strip().lower()
        name = input("Name: ").strip() or "Becoming the Heartbeat"
        password = getpass.getpass("Password: ")
        if User.query.filter_by(email=email).first():
            print("User exists.")
            return
        u = User(
            email=email,
            name=name,
            password_hash=generate_password_hash(password),
            onboarding_complete=True,
        )
        db.session.add(u)
        db.session.flush()
        for n in ["Family", "Friends", "Myself", "Fast Hands Drum Studio", "Work", "Other"]:
            db.session.add(LifeArea(user_id=u.id, name=n))
        db.session.commit()
        print("User created.")

    return app

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

app = create_app()
