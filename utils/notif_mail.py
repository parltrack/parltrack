import jinja2
from config import ROOT_URL
from flask_mail import Message
from os.path import abspath, dirname
from utils.utils import format_dict
from webapp import mail, app
from utils import contextdiff

template_dir = dirname(abspath(__file__))+'/../templates'

def send_html_mail(recipients, subject, obj, change, date, url, text):
    templateLoader = jinja2.FileSystemLoader(searchpath=template_dir)
    env = jinja2.Environment(autoescape=True, loader=templateLoader)
    env.filters['printdict'] = format_dict
    body=contextdiff.nesteddiff(obj, change, contextdiff.mail)
    template = env.get_template("notif_mail.html")
    outputText = template.render(
        changes=change,
        subject=subject,
        body=body,
        date=date,
        url=url
    )

    for recipient in recipients:
        msg = Message(subject,
                sender = "parltrack@parltrack.org",
                recipients=[recipient])
        msg.html = outputText
        msg.body = text
        with app.app_context():
            mail.send(msg)
