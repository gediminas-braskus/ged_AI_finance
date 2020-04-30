import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    username = db.execute("SELECT username FROM users WHERE id = :user_id", user_id = session['user_id'])[0]["username"]
    portfolio = db.execute("SELECT stock, symbol, SUM(shares) as shares, SUM(price * shares) as bought_total FROM buy WHERE username = :username GROUP BY stock, symbol", username=username)
    grand_total = 0
    bought_grand_total = 0
    for p in portfolio:
        p["price"] = lookup(p["symbol"])["price"]
        p["total"] = p["shares"] * p["price"]
        grand_total += p["total"]
        p["gain"] = p["total"] - p["bought_total"]
        bought_grand_total += p["bought_total"]
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session['user_id'])[0]["cash"]
    grand_total += cash
    bought_grand_total += cash
    gain_total = grand_total - bought_grand_total
    return render_template("index.html", portfolio=portfolio, cash=cash, grand_total=grand_total, bought_grand_total=bought_grand_total, gain_total=gain_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide stock's symbol", 400)
        validation = lookup(request.form.get("symbol"))
        if not validation:
            return apology("must provide valid stock's symbol", 400)
        elif not request.form.get("shares").isdigit():
            return apology("invalid shares", 400)

        price = lookup(request.form.get("symbol"))["price"]
        stock = lookup(request.form.get("symbol"))["name"]
        symbol = lookup(request.form.get("symbol"))["symbol"]
        shares = int(request.form.get("shares"))
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session['user_id'])[0]["cash"]
        balance = cash - (price * shares)
        if balance < 0:
            return apology("you don't have enough money", 403)
        else:
            db.execute("UPDATE users SET cash = :balance WHERE id = :user_id", balance = balance, user_id = session['user_id'])
            username = db.execute("SELECT username FROM users WHERE id = :user_id", user_id = session['user_id'])[0]["username"]
            db.execute("INSERT INTO buy (price, username, shares, stock, symbol) VALUES(:price, :username, :shares, :stock, :symbol)", price=price, username=username, shares=shares, stock=stock, symbol=symbol)
            db.execute("INSERT INTO archive (username, stock, symbol, shares, price) VALUES(:username, :stock, :symbol, :shares, :price)", username=username, stock=stock, symbol=symbol, shares=shares, price=price)
            flash("Bought!", "bought")
            return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    registered_usernames = db.execute("SELECT username FROM users")

    for registered_username in registered_usernames:
        if username == registered_username["username"]:
            return jsonify(False)

    if len(username) < 1:
        return jsonify(False)

    return jsonify(True)

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    username = db.execute("SELECT username FROM users WHERE id = :user_id", user_id = session['user_id'])[0]["username"]
    history = db.execute("SELECT stock, symbol, shares, price, date FROM archive WHERE username = :username", username=username)
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide stock's symbol", 400)
        validation = lookup(request.form.get("symbol"))
        if not validation:
            return apology("must provide valid stock's symbol", 400)

        quoted = lookup(request.form.get("symbol"))
        name = quoted["name"]
        symbol = quoted["symbol"]
        price = quoted["price"]
        return render_template("quoted.html", name=name, symbol=symbol, price=price)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords didn't match", 400)

        username = request.form.get("username")
        registered_usernames = db.execute("SELECT username FROM users")

        for registered_username in registered_usernames:
            if registered_username["username"] == username:
                return apology("username already exists", 400)

        db.execute("INSERT INTO users (username, hash) VALUES(:username, :password)", username=request.form.get("username"), password=generate_password_hash(request.form.get("password")))

        flash("Registration went successfully!", "registration")
        return redirect("/login")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("select stock which you want to sell", 400)
        elif not request.form.get("shares"):
            return apology("type number of shares you want to sell", 400)
        username = db.execute("SELECT username FROM users WHERE id = :user_id", user_id = session['user_id'])[0]['username']
        symbol = request.form.get("symbol")
        price = lookup(symbol)["price"]
        stock = lookup(symbol)["name"]
        shares = int(request.form.get("shares"))
        user_shares = db.execute("SELECT symbol, SUM(shares) as shares FROM buy WHERE username = :username GROUP BY symbol", username=username)
        u_shares = []
        for u in user_shares:
            if u["symbol"] == symbol:
                u_shares.append(u["shares"])
        if shares > u_shares[0]:
            return apology("you don't have that many shares", 400)
        elif shares == u_shares[0]:
            db.execute("INSERT INTO archive (username, stock, symbol, shares, price) VALUES(:username, :stock, :symbol, -:shares, :price)", username=username, stock=stock, symbol=symbol, shares=shares, price=price)
            db.execute("DELETE FROM buy WHERE username = :username and stock = :stock and symbol = :symbol", username = username, stock = stock, symbol = symbol)
            total1 = price * shares
            cash1 = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session['user_id'])[0]["cash"]
            balance1 = total1 + cash1
            db.execute("UPDATE users SET cash = :balance1 WHERE id = :user_id", balance1=balance1, user_id=session['user_id'])
            flash("Sold!", "sold")
            return redirect("/")
        else:
            total = price * shares
            cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id = session['user_id'])[0]["cash"]
            balance = total + cash
            db.execute("UPDATE users SET cash = :balance WHERE id = :user_id", balance=balance, user_id=session['user_id'])
            db.execute("INSERT INTO buy (username, stock, symbol, shares, price) VALUES(:username, :stock, :symbol, -:shares, :price)", username=username, stock=stock, symbol=symbol, shares=shares, price=price)
            db.execute("INSERT INTO archive (username, stock, symbol, shares, price) VALUES(:username, :stock, :symbol, -:shares, :price)", username=username, stock=stock, symbol=symbol, shares=shares, price=price)
            flash("Sold!", "sold")
            return redirect("/")
    else:
        username = db.execute("SELECT username FROM users WHERE id = :user_id", user_id = session['user_id'])[0]['username']
        symbols = db.execute("SELECT symbol, SUM(shares) as shares FROM buy WHERE username = :username GROUP BY symbol", username = username)
        return render_template("sell.html", symbols=symbols)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)