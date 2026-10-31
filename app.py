
import os
from datetime import date, datetime

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "dev-key-change-before-deployment"
)
db_url = os.environ.get("DATABASE_URL", "sqlite:///finance.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Vui lòng đăng nhập để tiếp tục."


# ==================== DATABASE MODELS ====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    transactions = db.relationship(
        "Transaction",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(500), default="")
    type = db.Column(db.String(10), nullable=False)  # income / expense

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )


with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ==================== AUTHENTICATION ====================

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Vui lòng điền đầy đủ thông tin.", "error")
        elif len(username) > 80 or len(email) > 120:
            flash("Tên đăng nhập hoặc email quá dài.", "error")
        elif len(password) < 8:
            flash("Mật khẩu phải có ít nhất 8 ký tự.", "error")
        elif User.query.filter_by(username=username).first():
            flash("Tên đăng nhập đã tồn tại.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email đã được sử dụng.", "error")
        else:
            user = User(username=username, email=email)
            user.set_password(password)

            db.session.add(user)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash("Không thể tạo tài khoản. Hãy thử lại.", "error")
            else:
                flash("Đăng ký thành công! Hãy đăng nhập.", "success")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Tên đăng nhập hoặc mật khẩu không đúng.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Bạn đã đăng xuất.", "success")
    return redirect(url_for("login"))


# ==================== DASHBOARD ====================

@app.route("/")
@login_required
def dashboard():
    today = date.today()
    first_day = today.replace(day=1)

    base_query = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= first_day,
        Transaction.date <= today
    )

    income = db.session.query(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == "income",
        Transaction.date >= first_day,
        Transaction.date <= today
    ).scalar()

    expense = db.session.query(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == "expense",
        Transaction.date >= first_day,
        Transaction.date <= today
    ).scalar()

    recent = base_query.order_by(
        Transaction.date.desc(), Transaction.id.desc()
    ).limit(5).all()

    return render_template(
        "dashboard.html",
        income=income,
        expense=expense,
        balance=income - expense,
        recent=recent
    )


# ==================== TRANSACTIONS: CREATE / READ ====================

@app.route("/transactions")
@login_required
def transactions():
    items = Transaction.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Transaction.date.desc(), Transaction.id.desc()
    ).all()

    return render_template("transactions.html", transactions=items)


def save_transaction(item):
    try:
        amount = float(request.form.get("amount", ""))
        transaction_date = date.fromisoformat(
            request.form.get("date", "")
        )
    except (ValueError, TypeError):
        flash("Số tiền hoặc ngày không hợp lệ.", "error")
        return False

    category = request.form.get("category", "").strip()
    note = request.form.get("note", "").strip()
    transaction_type = request.form.get("type", "")

    if amount <= 0 or amount > 9999999999:
        flash("Số tiền phải lớn hơn 0 và nằm trong giới hạn cho phép.", "error")
        return False

    if not category or len(category) > 100 or len(note) > 500:
        flash("Danh mục hoặc ghi chú không hợp lệ.", "error")
        return False

    if transaction_type not in ("income", "expense"):
        flash("Loại giao dịch không hợp lệ.", "error")
        return False

    # Không cho phép ngày trong tương lai.
    if transaction_date > date.today():
        flash("Ngày giao dịch không được ở tương lai.", "error")
        return False

    item.amount = amount
    item.date = transaction_date
    item.category = category
    item.note = note
    item.type = transaction_type
    return True


@app.route("/transactions/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    if request.method == "POST":
        item = Transaction(user_id=current_user.id)

        if save_transaction(item):
            db.session.add(item)
            db.session.commit()
            flash("Đã thêm giao dịch.", "success")
            return redirect(url_for("transactions"))

    return render_template(
        "transaction_form.html",
        item=None,
        today=date.today().isoformat()
    )


# ==================== UPDATE / DELETE ====================

def get_owned_transaction(transaction_id):
    item = db.session.get(Transaction, transaction_id)

    # Không cho xem hoặc sửa giao dịch của tài khoản khác.
    if item is None or item.user_id != current_user.id:
        abort(404)

    return item


@app.route("/transactions/<int:transaction_id>/edit",
           methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    item = get_owned_transaction(transaction_id)

    if request.method == "POST" and save_transaction(item):
        db.session.commit()
        flash("Đã cập nhật giao dịch.", "success")
        return redirect(url_for("transactions"))

    return render_template(
        "transaction_form.html",
        item=item,
        today=date.today().isoformat()
    )


@app.route("/transactions/<int:transaction_id>/delete",
           methods=["POST"])
@login_required
def delete_transaction(transaction_id):
    item = get_owned_transaction(transaction_id)
    db.session.delete(item)
    db.session.commit()

    flash("Đã xóa giao dịch.", "success")
    return redirect(url_for("transactions"))


# ==================== START APPLICATION ====================

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
