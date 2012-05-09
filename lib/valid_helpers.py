import re

def valid_month(month):
      months = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December']
      if month.capitalize() in months:
          return month.capitalize()
      else:
          return None

def valid_day(day):
    if day and day.isdigit():
        if int(day) < 1 or int(day) > 31:
            return None
        else:
            return int(day)

def valid_year(year):
    if year and year.isdigit():
        if int(year) < 1900 or int(year) > 2020:
            return None
        else:
            return int(year)

# Helpers for signup form
def valid_username(username):
    USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
    return username and USER_RE.match(username)

def valid_password(password):
    PASS_RE = re.compile(r"^.{3,20}$")
    return password and PASS_RE.match(password)

def valid_verify(password, verify):
    return password == verify

def valid_email(email):
    EMAIL_RE = re.compile(r"^[\S]+@[\S]+\.[\S]+$")
    return  EMAIL_RE.match(email)
