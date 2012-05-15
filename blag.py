import os
import sys
import webapp2
import json
import jinja2
import datetime
import time
import markupsafe
from markupsafe import Markup, escape
from google.appengine.ext import db
from webapp2_extras import sessions

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

import markdown2
import auth_helpers
import valid_helpers


class Handler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now_add = True)
    is_draft = db.BooleanProperty()
   
class MainPage(Handler):
    def get(self):
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = FALSE ORDER BY created DESC")
        self.render("main.html", posts=posts)
    
class JsonPostHandler(Handler):
    def get(self):
        self.response.headers['Content-type'] = 'application/json'
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = FALSE ORDER BY created DESC")
        post_dict = []
        for my_post in posts:
            post_dict.append({"subject" : my_post.subject, "content" : my_post.content, 
                            "created" : my_post.created.strftime('%a %b %d %H:%M:%S %Y'),
                            "last_modified" : my_post.last_modified.strftime('%a %b %d %H:%M:%S %Y')})

        self.write(json.dumps(post_dict))

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
                self.redirect('/')
        else:
            error = "Both subject and content please!"
            self.render("newpost.html", subject = subject, content = content, error = error)


class ShowPostHandler(Handler):
    def get(self, post_id):
        my_post = Post.get_by_id(int(post_id))
        self.render("showpost.html", my_post = my_post)

class ShowPostJsonHandler(Handler):
    def get(self, post_id):
        self.response.headers['Content-type'] = 'application/json'
        my_post = Post.get_by_id(int(post_id))
        post_dict = {"subject" : my_post.subject, "content" : my_post.content, 
                    "created" : my_post.created.strftime('%a %b %d %H:%M:%S %Y'),
                    "last_modified" : my_post.last_modified.strftime('%a %b %d %H:%M:%S %Y')}
        self.write(json.dumps(post_dict))

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
       
class User(db.Model):
    email = db.StringProperty(required = True)
    encrypted_pass = db.StringProperty(required = True)

class RegisterHandler(Handler):
    def get(self):
        self.render("register_form.html")

    def post(self):
        user_email  = self.request.get("email")
        user_password = self.request.get("password")
        user_verify = self.request.get("verify")
        
        check_email = valid_helpers.valid_email(user_email)
        check_password = valid_helpers.valid_password(user_password)
        check_verify = valid_helpers.valid_verify(user_password, user_verify)

        params = dict(user_email = user_email)
        have_error = False
        query = User.all(keys_only = True).filter("email", user_email)
        if not(check_email):
            params['error_email'] = "Thats an invalid email"
            have_error = True
        if not(check_password):
            params['error_password'] = "Thats not a valid password"
            have_error = True
        if not(check_verify):
            params['error_verify'] = "Your passwords don't match"
            have_error = True
        if not have_error:
            existing_user = query.get()
            if existing_user:
                params["error_email"] = "A user with this email already exists"
                have_error = True
        if have_error:
            self.render("register_form.html", **params)
        else:
            encrypted_pass = auth_helpers.make_pw_hash(user_email, user_password)
            user = User(email = user_email, encrypted_pass = encrypted_pass)
            user.put()
            existing_user = query.get()
            user_id = existing_user.id()
            user_hash = auth_helpers.make_secure_val(str(user_id))
            self.response.headers.add_header("Set-Cookie", "user_id = %s" % str(user_hash))
            self.redirect('/')

class LoginHandler(Handler):
    def post(self):
        user_email = self.request.get("email")
        user_password = self.request.get("password")
        query = User.all().filter("email", user_email)
        user = query.get()
        params = dict(user_email = user_email)
        if user:
            check_authentic_user = auth_helpers.valid_pw(user_email, user_password, user.encrypted_pass)
            if check_authentic_user:
                user_hash = auth_helpers.make_secure_val(str(user.key().id()))
                #TODO: set flash message
                self.response.headers.add_header("Set-Cookie", "user_id = %s" % str(user_hash))
                self.redirect('/archives')
            else:
                #TODO: set flash message
                params["error_login"] = "Invalid email/password combination"
                self.redirect('/')
        else:
            #TODO: set flash message
            params["error_login"] = "Invalid email/password combination"
            self.redirect('/')


app = webapp2.WSGIApplication([('/', MainPage),
                               ('/.json', JsonPostHandler),
                               ('/newpost', NewPostHandler),
                               ('/archives', ArchiveHandler),
                               ('/register', RegisterHandler),
                               ('/login', LoginHandler),
                               ('/post/(\d+)', ShowPostHandler),
                               ('/post/(\d+).json', ShowPostJsonHandler),
                               ('/post/(\d+)/edit', EditPostHandler),
                               ('/post/(\d+)/delete', DeletePostHandler),
                               ('/feeds/all.atom.xml', XMLHandler),
                               ('/drafts',DraftHandler)], debug=True)
