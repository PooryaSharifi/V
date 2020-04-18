from datetime import datetime, timedelta
from static import weather_host, weather_key
import requests
import config
import shelve
weathers_dir = __file__[0: __file__.index('/tools')] + '/static/weathers.dat'
weathers = shelve.open(weathers_dir)


async def weather(area):
    now = datetime.now()
    now -= timedelta(microseconds=now.microsecond, seconds=now.second, minutes=now.minute)
    key = str((area, now))
    if key not in weathers:
        async with config.session.get(weather_host + '/data/2.5/weather', params={
            'q': area,
            'appid': weather_key
        }) as response:
            _json = await response.json()
            print(_json)
            data = {
                'temperature': round(_json['main']['temp'] - 273.15, 1),
                'humidity': _json['main']['humidity'],
                'wind': _json['wind']['speed'],
                'condition': _json['weather'][0]['main'],
                '_date': now,
                'date': datetime.fromtimestamp(_json['dt']),
                'location': [_json['coord']['lat'], _json['coord']['lon']],
                'sun': {
                    'rise': datetime.fromtimestamp(_json['sys']['sunrise']),
                    'set': datetime.fromtimestamp(_json['sys']['sunset'])
                }
            }
            weathers[key] = data
            return data
    return weathers[key]


if __name__ == '__main__':
    print(requests.get(weather_host + '/data/2.5/weather', params={'q': 'tehran', 'appid': weather_key}).json())
