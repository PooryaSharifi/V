from config import app, wrk
from ego import blu as ego
from motion import blu as motion
from scenario import blu as scenario
from tools.ql import blu as ql
from spy import blu as spy
from client import blu as client
from client.simulator.v06 import blu as simulator
from client.bi import blu as bi
from sanic.response import redirect, text
from contact import blu as contact
from ha import blu as ha
import os
import subprocess
import ssl
# from sanic_cors import CORS
# CORS(app)
# pub_ip = subprocess.check_output(['dig', '+short', 'myip.opendns.com', '@resolver1.opendns.com']).decode().strip()


app.blueprint(ego)
app.blueprint(scenario)
app.blueprint(ql)
app.blueprint(motion)
app.blueprint(spy)
app.blueprint(contact)
app.blueprint(client)
app.blueprint(simulator)
app.blueprint(bi)
app.blueprint(ha)
app.static('/static', os.path.dirname(os.path.abspath(__file__)) + '/static')
app.static('/firebase-messaging-sw.js', os.path.dirname(os.path.abspath(__file__)) + '/static/firebase-messaging-sw.js', name='sw')
app.static('/.well-known/acme-challenge/YVhRdlB957z8dha_C3F6BK76DFyIKmnrUPsnS1f9qY8', os.path.dirname(os.path.abspath(__file__)) + '/static/ssl/YVhRdlB957z8dha_C3F6BK76DFyIKmnrUPsnS1f9qY8', name='ssl-1')
app.static('/.well-known/acme-challenge/hIHIKAGduYkMvDVtTcUWRQZI7AqtGdSWmyNpRbPHi1o', os.path.dirname(os.path.abspath(__file__)) + '/static/ssl/hIHIKAGduYkMvDVtTcUWRQZI7AqtGdSWmyNpRbPHi1o', name='ssl-2')
app.add_route(lambda _: redirect('/static/favicon.png'), '/favicon.ico')
# app.add_route(lambda _: redirect('/static/firebase-messaging-sw.js'), '/firebase-messaging-sw.js')
app.add_route(lambda _: redirect('/static/ractive.js'), '/static/ractive.min.js.map')
# app.add_route(lambda _: redirect('/static/google83c8bbff4f6e50f3.html'), '/google83c8bbff4f6e50f3.html')
# app.add_route(lambda _: redirect('http://{ip}/v0.2/client'.format(ip=pub_ip)), '/')
app.add_route(lambda _: redirect('/v0.2/client'), '/')
app.add_route(lambda _: text(''), '/server-status')

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context

context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain(
    os.path.dirname(os.path.abspath(__file__)) + '/certificate/certificate.pem',
    keyfile=os.path.dirname(os.path.abspath(__file__)) + '/certificate/private.pem',
)

# _ssl = {
#     'key': os.path.dirname(os.path.abspath(__file__)) + '/private.key',
#     'cert': os.path.dirname(os.path.abspath(__file__)) + '/certificate.crt',
# }

if __name__ == '__main__':
    app.run(host="0.0.0.0", workers=wrk, port=5050, ssl=None)  # , debug=False, log_config=None, access_log=False, )
