from client import host, tehran, admin_key
import requests
# from tools.ego import decrypt
from tools.maths import rnd
from datetime import datetime, timedelta
import time
from flask import Flask, request
import threading
from ast import literal_eval
app = Flask(__name__)
matches = []


@app.route('/<motor>', methods=['POST'])
def msg(motor):
    matches.append((motor, literal_eval(request.values['path'])))
    return 'Hello, World!'


client_server = threading.Thread(target=app.run, kwargs={'port': 5002})
client_server.start()


'''
        solve() -> notification list -> (two extra end point for test (retrieve msg for this porter))
            for each P: retrieve msgs -> ack path ->
                with google map| osrm: make route -> move -> send location -> at -> done

        request for each path location
'''

requests.delete(host + '/food/!!/shifts', data={'key': admin_key, 'q': '{}'})
requests.delete(host + '/food/!!/paths', data={'key': admin_key, 'q': '{}'})
requests.delete(host + '/food/!!/credits', data={'key': admin_key, 'q': '{}'})
# get a B key
requests.put(host + '/food/mehrad', data={'key': admin_key})
response = requests.post(host + '/food/mehrad@privilege=b', data={'key': admin_key})
requests.post(host + '/food/mehrad@credit=2', data={'key': admin_key})
b_key = response.text

# get two O key
requests.put(host + '/food/shahin', data={'key': b_key})
requests.put(host + '/food/alireza', data={'key': b_key})

os = []
response = requests.post(host + '/food/shahin@privilege=o', data={'key': b_key})
os.append(response.text)
response = requests.post(host + '/food/alireza@privilege=o', data={'key': b_key})
os.append(response.text)

# get 3 P key ->

ps = []

response = requests.put(host + '/food/masoud', data={'key': os[0]})
ps.append(response.text)
response = requests.put(host + '/food/mohsen', data={'key': os[1]})
ps.append(response.text)
response = requests.put(host + '/food/pouya', data={'key': os[1]})
ps.append(response.text)

# for each P: insert shift |-------|
#                         |----||---|

now = datetime.now()
for i in range(-4, 6):
    head = now + i * timedelta(seconds=1)
    tail = head + timedelta(seconds=4)
    requests.post(host + '/food/masoud@shifts={}:{}:{};{}:{}:{}'.format(
        head.hour, head.minute, head.second,
        tail.hour, tail.minute, tail.second,
    ), data={'key': ps[0], 'fcm': 'masoud', 'capacity': 20})
# requests.post(host + '/food/masoud@shifts=20;{}:{}:{};{}:{}:{}'.format(
#     now.hour, now.minute, 0,
#     now.hour, now.minute + 1, 30
# ), data={'key': ps[0]})
# requests.post(host + '/food/mohsen@shifts=30;{}:{}:{};{}:{}:{}'.format(
#     now.hour, now.minute, 10,
#     now.hour, now.minute + 1, 40
# ), data={'key': ps[1]})
# requests.post(host + '/food/masoud@shifts=60;{}:{}:{};{}:{}:{}'.format(
#     now.hour, now.minute + 1, 45,
#     now.hour, now.minute + 2, 0
# ), data={'key': ps[0]})
# ##

# insert orders randomly
requests.post(host + '/food/~{},{};{},{}'.format(*rnd(tehran), *rnd(tehran)), data={
    'key': os[0],
    'volume': 2,
    'priority': 1,
    'delay': 400
})

requests.post(host + '/food/~{},{};{},{}'.format(*rnd(tehran), *rnd(tehran)), data={
    'key': os[1],
    'volume': 5,
    'priority': 6,
    'delay': 1300
})

requests.post(host + '/food/~{},{};{},{}'.format(*rnd(tehran), *rnd(tehran)), data={
    'key': os[0],
    'volume': 17,
    'priority': 2,
})

# time.sleep(.5)
#
# print(ps[0])
# t1 = threading.Thread(target=lambda: requests.post(host + '/~~/food/masoud', data={'key': ps[0]}))
# t2 = threading.Thread(target=lambda: requests.post(host + '/~~/food/masoud', data={'key': ps[0]}))
# t3 = threading.Thread(target=lambda: requests.post(host + '/~~/food/masoud', data={'key': ps[0]}))
# t1.start()
# t2.start()
# requests.post(host + '/~~/food/masoud', data={'key': ps[0]})
# # active porters to porters
# while True:
#     requests.patch(host + '/food', data={'key': os[0]})
#     time.sleep(5)

# send some random location. for mohsen and masoud.
requests.post(host + '/food/masoud@{},{}'.format(*rnd(tehran)), data={'key': ps[0]})  # <- this
requests.post(host + '/food/mohsen@{},{}'.format(*rnd(tehran)), data={'key': ps[1]})


requests.patch(host + '/food', data={'key': os[0]})
# response = requests.post(host + '/food/@frees', data={'key': os[0]})

# send some random location. for mohsen and masoud.
requests.post(host + '/food/masoud@{},{}'.format(*rnd(tehran)), data={'key': ps[0]})  # <- this
requests.post(host + '/food/mohsen@{},{}'.format(*rnd(tehran)), data={'key': ps[1]})

# solve
# requests.post(host + '/food/!!!/rnd', data={'key': b_key})
# requests.post(host + '/food/!!!/grd', data={'key': b_key})
requests.post(host + '/food/!!!/hng', data={'key': b_key})

# wait for ack
time.sleep(.5)
response = requests.post(host + '/food/~{}@ack'.format(matches[0][1]['_id']), data={'key': ps[0]})

# get path location
response = requests.get(host + '/food/~{}@'.format(matches[0][1]['_id']), params={'key': os[0]})
print(response.text)

response = requests.get(host + '/food/masoud@', params={'key': os[0]})
print(response.text)

response = requests.post(host + '/food/~{}@done'.format(matches[0][1]['_id']), data={'key': ps[0]})
print(response.text)
