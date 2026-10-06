import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "login"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False, default="SUMbody")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LifeArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SumEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    life_area_id = db.Column(db.Integer, db.ForeignKey("life_area.id"), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    value = db.Column(db.Integer, nullable=False)
    communicated = db.Column(db.Boolean, nullable=True)
    occurred_on = db.Column(db.Date, nullable=False, index=True)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    legacy_timestamp = db.Column(db.String(80), nullable=True)
    archived = db.Column(db.Boolean, default=False, nullable=False, index=True)
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

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    with app.app_context():
        db.create_all()
        # Lightweight SQLite migrations for existing installations.
        columns = {row[1] for row in db.session.execute(db.text("PRAGMA table_info(sum_entry)"))}
        if "archived" not in columns:
            db.session.execute(db.text("ALTER TABLE sum_entry ADD COLUMN archived BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()

    @app.context_processor
    def globals():
        context = {"today": local_today(), "composer_areas": []}
        if current_user.is_authenticated:
            context["composer_areas"] = LifeArea.query.filter_by(
                user_id=current_user.id, active=True
            ).order_by(LifeArea.name).all()
        return context

    @app.route("/")
    @login_required
    def home():
        today = local_today()
        yesterday = today - timedelta(days=1)

        def totals(day):
            q = SumEntry.query.filter_by(user_id=current_user.id, occurred_on=day, archived=False)
            value = db.session.query(func.coalesce(func.sum(SumEntry.value), 0)).filter_by(
                user_id=current_user.id, occurred_on=day, archived=False
            ).scalar()
            return q.count(), value

        today_count, today_value = totals(today)
        yesterday_count, yesterday_value = totals(yesterday)
        recent = SumEntry.query.filter_by(
            user_id=current_user.id, occurred_on=today, archived=False
        ).order_by(SumEntry.logged_at.desc()).limit(8).all()
        return render_template(
            "home.html",
            today_count=today_count,
            today_value=today_value,
            yesterday_count=yesterday_count,
            yesterday_value=yesterday_value,
            recent=recent,
        )

    @app.route("/add", methods=["GET", "POST"])
    @login_required
    def add_sum():
        areas = LifeArea.query.filter_by(
            user_id=current_user.id, active=True
        ).order_by(LifeArea.name).all()
        if request.method == "POST":
            description = request.form.get("description", "").strip()
            try:
                value = int(request.form.get("value", ""))
                area_id = int(request.form.get("life_area_id", ""))
                occurred_on = datetime.strptime(
                    request.form.get("occurred_on", ""), "%Y-%m-%d"
                ).date()
            except (ValueError, TypeError):
                flash("Please complete all fields.", "error")
                return render_template("add.html", areas=areas)
            area = LifeArea.query.filter_by(
                id=area_id, user_id=current_user.id, active=True
            ).first()
            if not description or not area or value not in range(1, 6):
                flash("Please complete all fields.", "error")
                return render_template("add.html", areas=areas)
            comm = request.form.get("communicated")
            entry = SumEntry(
                user_id=current_user.id,
                life_area_id=area.id,
                description=description,
                value=value,
                communicated=True if comm == "yes" else False if comm == "no" else None,
                occurred_on=occurred_on,
            )
            db.session.add(entry)
            db.session.commit()
            flash("SUM added.", "success")
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
        total_value = q.with_entities(func.coalesce(func.sum(SumEntry.value), 0)).scalar()
        entries = q.order_by(
            SumEntry.occurred_on.desc(), SumEntry.logged_at.desc()
        ).limit(500).all()
        areas = LifeArea.query.filter_by(
            user_id=current_user.id
        ).order_by(LifeArea.name).all()
        return render_template(
            "history.html",
            entries=entries,
            total_count=total_count,
            total_value=total_value,
            areas=areas,
            archived_view=archived_view,
        )

    @app.route("/insights")
    @login_required
    def insights():
        entries = SumEntry.query.filter_by(user_id=current_user.id, archived=False).all()
        total_count = len(entries)
        total_value = sum(e.value for e in entries)
        by_area = db.session.query(
            LifeArea.name,
            func.count(SumEntry.id),
            func.coalesce(func.sum(SumEntry.value), 0),
        ).join(SumEntry).filter(
            SumEntry.user_id == current_user.id,
            SumEntry.archived.is_(False),
        ).group_by(LifeArea.id).order_by(func.sum(SumEntry.value).desc()).all()
        days = db.session.query(
            SumEntry.occurred_on,
            func.count(SumEntry.id),
            func.sum(SumEntry.value),
        ).filter_by(user_id=current_user.id, archived=False).group_by(SumEntry.occurred_on).all()
        most_active = max(days, key=lambda x: x[1]) if days else None
        highest_value = max(days, key=lambda x: x[2]) if days else None
        communicated = sum(1 for e in entries if e.communicated is True)
        comm_known = sum(1 for e in entries if e.communicated is not None)
        return render_template(
            "insights.html",
            total_count=total_count,
            total_value=total_value,
            avg=(total_value / total_count if total_count else 0),
            by_area=by_area,
            most_active=most_active,
            highest_value=highest_value,
            communicated=communicated,
            comm_known=comm_known,
        )

    @app.route("/areas", methods=["GET", "POST"])
    @login_required
    def areas():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if name and not LifeArea.query.filter(
                func.lower(LifeArea.name) == name.lower(),
                LifeArea.user_id == current_user.id,
            ).first():
                db.session.add(LifeArea(user_id=current_user.id, name=name))
                db.session.commit()
            return redirect(url_for("areas"))
        return render_template(
            "areas.html",
            areas=LifeArea.query.filter_by(user_id=current_user.id)
            .order_by(LifeArea.active.desc(), LifeArea.name).all(),
        )

    @app.post("/areas/<int:area_id>/toggle")
    @login_required
    def toggle_area(area_id):
        area = LifeArea.query.filter_by(
            id=area_id, user_id=current_user.id
        ).first_or_404()
        area.active = not area.active
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
        flash("Tip restored." if not entry.archived else "Tip archived.", "success")
        return redirect(request.referrer or url_for("history"))

    @app.route("/goals", methods=["GET", "POST"])
    @login_required
    def goals():
        active_areas = LifeArea.query.filter_by(
            user_id=current_user.id, active=True
        ).order_by(LifeArea.name).all()
        if request.method == "POST":
            intention = request.form.get("intention", "").strip()
            target = request.form.get("target", "").strip() or None
            area_id = request.form.get("life_area_id", type=int)
            area = LifeArea.query.filter_by(
                id=area_id, user_id=current_user.id, active=True
            ).first()
            if not intention or not area:
                flash("Choose a Life Area and write your intention.", "error")
            else:
                db.session.add(Goal(
                    user_id=current_user.id,
                    life_area_id=area.id,
                    intention=intention,
                    target=target,
                ))
                db.session.commit()
                flash("Goal added.", "success")
            return redirect(url_for("goals"))
        user_goals = Goal.query.filter_by(user_id=current_user.id).order_by(
            Goal.active.desc(), Goal.created_at.desc()
        ).all()
        return render_template("goals.html", goals=user_goals, areas=active_areas)

    @app.post("/goals/<int:goal_id>/toggle")
    @login_required
    def toggle_goal(goal_id):
        goal = Goal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
        goal.active = not goal.active
        db.session.commit()
        return redirect(url_for("goals"))

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
                return redirect(url_for("home"))
            flash("Email or password not recognized.", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.cli.command("create-user")
    def create_user():
        import getpass
        email = input("Email: ").strip().lower()
        name = input("Name: ").strip() or "SUMbody"
        password = getpass.getpass("Password: ")
        if User.query.filter_by(email=email).first():
            print("User exists.")
            return
        u = User(
            email=email,
            name=name,
            password_hash=generate_password_hash(password),
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
