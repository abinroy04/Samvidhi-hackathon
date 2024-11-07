import os
import pymysql
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, session, request

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')

# MySQL connection details
db_host = os.environ.get('DB_HOST', 'localhost')
db_user = os.environ.get('DB_USER', 'root')
db_password = os.environ.get('DB_PASSWORD', '12345')
db_name = os.environ.get('DB_NAME', 'abintest')

def get_db_connection():
    """
    Get a connection to the MySQL database.
    """
    return pymysql.connect(
        host=db_host,
        user=db_user,
        password=db_password,
        database=db_name
    )

@app.template_filter('enumerate')
def enumerate_filter(data):
    """
    Custom Jinja2 filter to enumerate a list.
    """
    return enumerate(data, start=1)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handle user login.
    """
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE username = %s AND password = %s", (username, password))
        user = cur.fetchone()

        if user:
            session['user_id'] = user[0]
            conn.close()
            return redirect(url_for('dashboard'))
        else:
            conn.close()
            return render_template('login.html', error='Invalid username or password')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handle new user registration (without password hashing).
    """
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()

        # Check if the username already exists
        cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            return render_template('register.html', error='Username already exists')

        # Insert the new user into the database without password hashing
        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
        conn.commit()

        conn.close()

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    """
    Display the user's screen time and token balance.
    """
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = get_db_connection()
    cur = conn.cursor()

    # Get screen time data
    cur.execute("SELECT week, minutes FROM screen_time WHERE user_id = %s ORDER BY week DESC", (user_id,))
    screen_time_data = cur.fetchall()

    # Get token balance (check if a result is returned)
    cur.execute("SELECT total_tokens FROM tokens WHERE user_id = %s", (user_id,))
    token_balance_result = cur.fetchone()

    # If no result is found, set token_balance to 0
    if token_balance_result:
        token_balance = token_balance_result[0]
    else:
        token_balance = 0

    conn.close()

    return render_template('dashboard.html', screen_time_data=screen_time_data, token_balance=token_balance)

@app.route('/leaderboard')
def leaderboard():
    """
    Display a leaderboard of users ranked by their reduction in screen time.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Get the latest week's screen time data
    cur.execute("SELECT user_id, minutes FROM screen_time WHERE week = (SELECT MAX(week) FROM screen_time)")
    latest_screen_time = {user_id: minutes for user_id, minutes in cur.fetchall()}

    # Get the previous week's screen time data
    cur.execute("SELECT user_id, minutes FROM screen_time WHERE week = (SELECT MAX(week) FROM screen_time) - INTERVAL 1 WEEK")
    prev_screen_time = {user_id: minutes for user_id, minutes in cur.fetchall()}

    # Calculate the screen time reduction for each user
    screen_time_reduction = {}
    for user_id in latest_screen_time:
        if user_id in prev_screen_time:
            reduction = prev_screen_time[user_id] - latest_screen_time[user_id]
            screen_time_reduction[user_id] = reduction

    # Get the user details and sort by screen time reduction
    cur.execute("""
    SELECT u.username, st.minutes - COALESCE(prev.minutes, 0) AS reduction
    FROM users u
    LEFT JOIN screen_time st ON u.user_id = st.user_id AND st.week = (SELECT MAX(week) FROM screen_time)
    LEFT JOIN (SELECT user_id, minutes FROM screen_time WHERE week = (SELECT MAX(week) FROM screen_time) - INTERVAL 1 WEEK) prev ON u.user_id = prev.user_id
    ORDER BY reduction DESC""")


    leaderboard_data = cur.fetchall()

    conn.close()

    return render_template('leaderboard.html', leaderboard_data=leaderboard_data)

@app.route('/logout')
def logout():
    """
    Handle user logout.
    """
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/update_tokens')
def update_tokens():
    """
    Update the tokens for each user based on their screen time reduction.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Get the latest week's screen time data
    cur.execute("SELECT user_id, minutes FROM screen_time WHERE week = (SELECT MAX(week) FROM screen_time)")
    latest_screen_time = {user_id: minutes for user_id, minutes in cur.fetchall()}

    # Get the previous week's screen time data
    cur.execute("SELECT user_id, minutes FROM screen_time WHERE week = (SELECT MAX(week) FROM screen_time) - INTERVAL 1 WEEK")
    prev_screen_time = {user_id: minutes for user_id, minutes in cur.fetchall()}

    # Calculate the screen time reduction for each user and update their tokens
    for user_id in latest_screen_time:
        if user_id in prev_screen_time:
            reduction = prev_screen_time[user_id] - latest_screen_time[user_id]
            tokens_earned = int(reduction * 1.67)
            cur.execute("UPDATE tokens SET total_tokens = total_tokens + %s WHERE user_id = %s", (tokens_earned, user_id))

    conn.commit()
    conn.close()

    return redirect(url_for('leaderboard'))

@app.route('/')
def home():
    """
    Redirect to the login page if no session exists; otherwise, go to the dashboard.
    """
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)