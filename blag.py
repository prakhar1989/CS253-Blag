import os
import sys
import webapp2
import jinja2
import datetime
import time
import markupsafe
from markupsafe import Markup, escape
from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

import markdown2

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
    is_draft = db.BooleanProperty()
   
class MainPage(Handler):
    def get(self):
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = FALSE ORDER BY created DESC")
        self.render("main.html", posts=posts)
    
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
        # my_query = db.GqlQuery("SELECT * FROM Post where __key__ = KEY('Post', " +  post_id + ")")
        my_post = Post.get_by_id(int(post_id))
        self.render("showpost.html", my_post = my_post)

class DraftHandler(Handler):
    def get(self):
        posts = db.GqlQuery("SELECT * FROM Post WHERE is_draft = TRUE ORDER BY created DESC")
        self.render("main.html", posts=posts)

app = webapp2.WSGIApplication([('/', MainPage),
                               ('/newpost', NewPostHandler),
                               ('/post/(\d+)', ShowPostHandler),
                               ('/drafts',DraftHandler)], debug=True)
