from pytg.sender import Sender
from pytg.receiver import Receiver
import json
receiver = Receiver(host="localhost", port=4458)
sender = Sender(host="localhost", port=4458)

name = sender.contact_add("+989133657623", "+989133657623", "")[0]['print_name']
print(sender.send_msg(name, "hi h hi"))
print(sender.send_location(name, 31., 53.))
