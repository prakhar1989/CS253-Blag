import os
import sys
import webapp2
import json
import jinja2
import datetime
import time
import markupsafe
import logging
from markupsafe import Markup, escape
from google.appengine.ext import db
from google.appengine.api import memcache

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

import markdown2
import auth_helpers
import valid_helpers

### CACHE HELPERS ###

def get_top_posts(update = False):
    key = 'top'
    posts = memcache.get(key)
    last_time = memcache.get('last_time') # FOR SUBMISSION
    if last_time:
        last_queried = time.time() - last_time
    else:
        last_queried = 0
    if posts is None or update:
        logging.error("DB query")
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = FALSE ORDER BY created DESC")
        posts = list(posts)
        memcache.set(key, posts)
        memcache.set('last_time', time.time())
        last_queried = 0

    logging.error("Queried %ssecs ago" % int(last_queried))
    return posts, last_queried

def get_requested_post(post_id):
    my_post = memcache.get(post_id)
    last_time = memcache.get("(post_time, %s)" % post_id)
    if last_time:
        last_queried = time.time() - last_time
    else:
        last_queried = 0
    if my_post is None:
        my_post = Post.get_by_id(int(post_id))
        memcache.set(post_id, my_post)
        memcache.set("(post_time, %s)" % post_id, time.time())
        last_queried = 0
    return my_post, last_queried

### BASE HANDLER CLASS ###
class Handler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = auth_helpers.make_secure_val(val)
        self.response.headers.add_header(
                'Set-Cookie', "%s=%s; Path=/" % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and auth_helpers.check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))

def users_key(group = "default"):
    return db.Key.from_path('users', group)

### AUTH STUFF ###
class User(db.Model):
    username = db.StringProperty(required = True)
    email = db.StringProperty()
    pw_hash = db.StringProperty(required = True)

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('username =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email=None):
        pw_hash = auth_helpers.make_pw_hash(name, pw)
        return User(parent = users_key(),
                    username = name,
                    pw_hash = pw_hash,
                    email = email)
    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and auth_helpers.valid_pw(name, pw, u.pw_hash):
            return u

class SignupHandler(Handler):
    def get(self):
        self.render("signup_form.html")

    def post(self):
        have_error = False
        self.user_username = self.request.get('username')
        self.user_password = self.request.get('password')
        self.user_verify = self.request.get('verify')
        self.user_email = self.request.get('email')
        
        check_username = valid_helpers.valid_username(self.user_username)
        check_password = valid_helpers.valid_password(self.user_password)
        check_verify = valid_helpers.valid_verify(self.user_verify, self.user_password)
        check_email = valid_helpers.valid_email(self.user_email)

        params = dict(user_username = self.user_username, user_email = self.user_email)

        if not(check_username):
            params['error_username'] = "That's not a valid username."
            have_error = True
        if not(check_password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        if not(check_verify):
            params['error_verify'] = "Your passwords didn't match."
            have_error = True
        if not(check_email):
            params['error_email'] = "That's not a valid email."
            have_error = True
        if not have_error:
            existing_user = User.by_name(self.user_username)
            if existing_user:
                params['error_username'] = "This user already exists"
                have_error = True

        if have_error:
            self.render("signup_form.html", **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError

class RegisterHandler(SignupHandler):
    def done(self):
        u = User.register(self.user_username, self.user_password, self.user_email)
        u.put()
        self.login(u)
        self.redirect('/unit3/welcome')

class WelcomeHandler(Handler):
    def get(self):
        if self.user:
            self.write("<h1>Welcome, %s</h1>" % self.user.username)
        else:
            self.redirect('/signup')

class LoginHandler(Handler):
    def get(self):
        self.render("login.html")

    def post(self):
        user_username = self.request.get('username')
        user_password = self.request.get('password')
        params = dict(username = user_username)
        u = User.login(user_username, user_password)
        if u: 
            self.login(u)
            self.redirect('/unit3/welcome')
        else:
            params["error_username"] = "Invalid login"
            params["error_password"] = " "
            self.render("login.html", **params)

class LogoutHandler(Handler):
    def get(self):
        self.logout()
        self.redirect('/signup')

### BLOG STUFF ###
class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now_add = True)
    is_draft = db.BooleanProperty()

class MainPage(Handler):
    def get(self):
        posts, last_queried = get_top_posts() 
        self.render("main.html", posts=posts, last_queried = int(last_queried))
    
class JsonPostHandler(Handler):
    def get(self):
        self.response.headers['Content-type'] = 'application/json'
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = FALSE ORDER BY created DESC")
        post_dict = []
        for my_post in posts:
            post_dict.append({"subject" : my_post.subject, "content" : my_post.content, 
                            "created" : my_post.created.strftime('%a %b %d %H:%M:%S %Y'),
                            "last_modified" : my_post.last_modified.strftime('%a %b %d %H:%M:%S %Y')})

        self.write(json.dumps(post_dict, indent=4))

class NewPostHandler(Handler):
    def get(self):
        self.render("newpost.html")

    def post(self):
        subject = self.request.get("subject")
        content = Markup(markdown2.markdown(self.request.get("content")))
        is_draft = self.request.get("is_draft")
        
        if subject and content:
            p = Post(subject = subject, content = content, is_draft = (is_draft == "on"))
            p.put()
            if is_draft == "on":
                self.redirect('/drafts')
            else:
                get_top_posts(update = True)
                self.redirect('/')
        else:
            error = "Both subject and content please!"
            self.render("newpost.html", subject = subject, content = content, error = error)

class ShowPostHandler(Handler):
    def get(self, post_id):
        my_post, last_queried = get_requested_post(post_id)
        self.render("showpost.html", my_post = my_post, 
                                     last_queried = int(last_queried))

class ShowPostJsonHandler(Handler):
    def get(self, post_id):
        self.response.headers['Content-type'] = 'application/json'
        my_post = Post.get_by_id(int(post_id))
        post_dict = {"subject" : my_post.subject, "content" : my_post.content, 
                    "created" : my_post.created.strftime('%a %b %d %H:%M:%S %Y'),
                    "last_modified" : my_post.last_modified.strftime('%a %b %d %H:%M:%S %Y')}
        self.write(json.dumps(post_dict, indent=4))

class EditPostHandler(Handler):
    def get(self, post_id):
        my_post = Post.get_by_id(int(post_id))
        self.render("editpost.html", subject = my_post.subject, content = my_post.content)

    def post(self, post_id):
        subject = self.request.get("subject")
        content = Markup(markdown2.markdown(self.request.get("content")))
        last_modified = datetime.datetime.now()
        is_draft = self.request.get("is_draft")
        
        if subject and content:
            my_post = Post.get_by_id(int(post_id))
            my_post.subject = subject
            my_post.content = content
            my_post.is_draft = (is_draft == "on")
            my_post.put()

            if is_draft == "on":
                self.redirect('/drafts')
            else:
                self.redirect('/post/' + str(my_post.key().id()))
        else:
            error = "Both subject and content please!"
            self.render("editpost.html", subject = subject, content = content, error = error)

class DraftHandler(Handler):
    def get(self):
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = TRUE ORDER BY created DESC")
        self.render("main.html", posts=posts)

class ArchiveHandler(Handler):
    def get(self):
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = FALSE ORDER BY created DESC")
        self.render("archives.html", posts=posts)

class DeletePostHandler(Handler):
    def get(self, post_id):
        my_post = Post.get_by_id(int(post_id))
        my_post.delete()
        self.redirect('/')

class XMLHandler(Handler):
    def get(self):
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = FALSE ORDER BY created DESC")
        self.response.headers['Content-Type'] = 'application/atom+xml'
        self.render("xmltemplate.xml", posts=posts)

class FlushCacheHandler(Handler):
    def get(self):
        memcache.flush_all()
        self.redirect('/')
       


app = webapp2.WSGIApplication([('/', MainPage),
                               ('/.json', JsonPostHandler),
                               ('/newpost', NewPostHandler),
                               ('/archives', ArchiveHandler),
                               ('/register', RegisterHandler),
                               ('/signup', RegisterHandler),
                               ('/login', LoginHandler),
                               ('/unit3/welcome', WelcomeHandler),
                               ('/logout', LogoutHandler),
                               ('/post/(\d+)', ShowPostHandler),
                               ('/post/(\d+).json', ShowPostJsonHandler),
                               ('/post/(\d+)/edit', EditPostHandler),
                               ('/post/(\d+)/delete', DeletePostHandler),
                               ('/feeds/all.atom.xml', XMLHandler),
                               ('/flush', FlushCacheHandler),
                               ('/drafts',DraftHandler)], debug=True)
