from twofish import Twofish
from sanic import Blueprint
from sanic.exceptions import abort
from sanic.response import json
from functools import wraps
from datetime import datetime, timedelta
import config
from random import randint
import ujson
from werkzeug.security import generate_password_hash, check_password_hash
from tools.mu import manager as mu

T = Twofish(b'*secret*')
blu = Blueprint('ego', url_prefix='/v0.2')


def encrypt(privilege, user, hang, time):
    key = '{}.{}.{}.{}'.format(privilege, user, hang, int(time.timestamp() / 60)).ljust(32)
    return (T.encrypt(key[:16].encode()) + T.encrypt(key[16:].encode())).hex()


# print(encrypt('a', 'admin', '', datetime.now()))


def decrypt(key):
    key = bytes.fromhex(key)
    l = (T.decrypt(key[:16]) + T.decrypt(key[16:])).decode().rstrip().split('.')
    if len(l) != 4:
        raise Exception
    return tuple(l)


def privileges(roles):
    def decorator(f):
        @wraps(f)
        async def decorated_function(request, *args, **kwargs):
            if request.body and request.body[0] == ord('['):
                request.body = ujson.loads(request.body.decode('utf-8'))
                for key, value in request.body[0].items():
                    request.form[key] = [value]
            try:
                payload = decrypt(request.form['key'][0] if 'key' in request.form else request.args['key'][0])
            except:
                abort(403, "can't decrypt key")
            if payload[0] in roles:
                if 'hang' in kwargs and 'user' in kwargs and f.__name__ != 'branch':
                    ban(payload, kwargs['user'], kwargs['hang'])
                if int(payload[3]) > datetime.now().timestamp() / 60 - 8 * 60:
                    return await f(request, payload, *args, **kwargs)
                abort(403, 'your account expired prepare for some credits.')
            # print(f.__name__, payload[0])
            abort(403, ' or '.join(roles) + ' required')
        return decorated_function
    return decorator


def ban(payload, user, hang):
    if payload[2] != hang and payload[0] != 'a':
        abort(403, 'you are not in this hang')
    if payload[0] == 'p' and user != payload[1]:
        abort(403, 'access to another porter')


@blu.route('/<hang>/@credit=<credit:int>,@password=<password>', methods=['POST', 'PUT'])
@blu.route('/<hang>/@password=<password>,@credit=<credit:int>', methods=['POST', 'PUT'])
# @blu.route('/<hang>/<user>/@credit=<credit:int>', methods=['POST', 'PUT'])
@privileges({'a'})
async def credit(request, payload, hang, credit, password):
    now = datetime.now()
    await config.users.update_one({
        'user': hang
    }, {
        '$set': {
            '_date': now,
            'hang': hang,
            'user': hang,
            'password': generate_password_hash(password),
            'privilege': 'b',
            # 'credit': credit,
            'children': [],
            'parent': payload[1],
            'cash': 0.0,
            'population': 1,
            **({'email': request.form['email'][0]} if 'email' in request.form else {})
        },
        '$inc': {'credit': credit}
    }, True, True)
    return json({'SUCCESS': True, 'key': encrypt('b', hang, hang, now), 'password': password}, 201)  # must generate password


@blu.route('/<hang>/<user>/@password=<password>', methods=['GET'])
async def login(request, user, hang, password):
    user = await config.users.aggregate([
        {'$match': {'hang': hang, 'user': user}},
        {'$lookup': {
            'from': "users",
            'localField': "hang",
            'foreignField': "user",
            'as': "boss"
        }},
    ]).to_list(1)
    if not user:
        return json({'SUCCESS': False})
    user = user[0]
    del user['_id']
    user['_date'] = str(user['_date'])
    if user['boss'][0]['credit'] > 0 and check_password_hash(user['password'], password):
        del user['boss']
        return json({'SUCCESS': True, 'user': user, 'key': encrypt(user['privilege'], user['user'], hang, datetime.now())}, 200)
    del user['boss']
    return json({'SUCCESS': False, 'user': user})


@blu.route('/<hang>/<user>/@password=<password>', methods=['POST'])
@privileges({'a', 'b', 'o'})
async def signup(request, payload, user, hang, password):
    # ban(payload, user, hang)
    now = datetime.now()
    try:
        result = await config.users.insert_one({
            '_date': now,
            'hang': hang,
            'parent': hang,
            'user': user,
            'password': generate_password_hash(password),
            'privilege': 'u',
            'phone': '+989133657623' if 'phone' not in request.form else request.form['phone'][0]
        })
    except:
        return json({'SUCCESS': False})
    return json({'SUCCESS': True, 'key': encrypt('u', user, hang, now), 'password': password}, 201)


@blu.route('/<hang>/<user>', methods=['PATCH'])
@blu.route('/<hang>/<user>/@password=<password>', methods=['PATCH'])
@privileges({'a', 'b', 'o', 'p'})
async def branch(request, payload, user, hang, password=None):
    # ban(payload, user, hang)
    if not password:
        password = str(randint(10000, 99999))
    now = datetime.now()
    result = await config.users.update_one({
        'user': payload[1],
        'hang': hang,
        '$or': [{
            'children': {'$size': 0}
        }, {
            'children': {'$size': 1}
        }]
    }, {
        '$push': {'children': user}
    })
    if result.modified_count == 0:
        return json({'SUCCESS': False})

    await config.users.insert_one({
        '_date': now,
        'hang': hang,
        'user': user,
        'password': generate_password_hash(password),
        'privilege': 'p',

        'children': [],
        'parent': payload[1],
        'cash': 0.0,
        'population': 1
    })

    user = (await config.users.aggregate([
        {'$match': {'user': user, 'hang': hang}},
        {
            '$graphLookup': {
                'from': "users",
                'startWith': "$parent",
                'connectFromField': "parent",
                'connectToField': "user",
                'as': "hierarchy"
            }
        }
    ]).to_list(None))[0]

    await config.users.update_many({
        '_id': {'$in': [parent['_id'] for parent in user['hierarchy']]}
    }, {
        '$inc': {'population': 1}
    })

    return json({'SUCCESS': True, 'key': encrypt('p', user['user'], hang, now), 'password': password}, 201)


@blu.route('/<hang>/<user>/@token=<token>', methods=['POST'])
@privileges({'a', 'b', 'o', 'p'})
async def set_token(request, payload, user, hang, token):
    result = await config.users.update_one({'hang': hang, 'user': user}, {
        '$set': {
            'fcm': token
        }
    })
    return json({'SUCCESS': True}, 202)


@blu.route('/<hang>/<user>/@password=<password>', methods=['PUT'])
@privileges({'a', 'b', 'o', 'p'})
async def change_password(request, payload, user, hang, password):
    # ban(payload, user, hang)
    result = await config.users.update_one({'hang': hang, 'user': user}, {
        '$set': {
            'password': password
        }
    })
    #### if
    return json({'SUCCESS': True, 'key': encrypt('p', user, hang, datetime.now())}, 202)


@blu.route('/<hang>/<user>/@privilege=<privilege>', methods=['PUT'])
@privileges({'a', 'b', 'o'})
async def _privilege(request, payload, user, hang, privilege):
    # ban(payload, user, hang)
    if ord(payload[0]) >= ord(privilege):
        abort(403)
    result = await config.users.update_one({'hang': hang, 'user': user}, {
        '$set': {
            'privilege': privilege
        }
    })
    if result.modified_count == 0:
        abort(403)
    return json({'SUCCESS': True, 'key': encrypt(privilege, user, hang, datetime.now())}, 202)


@blu.route('/<hang>/<user>/@fcm=<fcm>', methods=['POST'])
@privileges({'a', 'b', 'o', 'u'})
async def _fcm(request, payload, user, hang, fcm):
    now = datetime.now()
    location = [0, 0]
    result = config.locations.insert_one({
        '_date': now,
        'territory': user,
        'hang': hang,
        'location': location,
        'fcm': fcm
    })
    if True:
        mu.observe(None, user, hang, location, now, fcm=fcm)
        return json({'SUCCESS': True})
    return json({})
