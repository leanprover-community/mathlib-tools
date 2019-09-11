import zulip

# Pass the path to your zuliprc file here.
client = zulip.Client(config_file="~/.zuliprc")

# Send a stream message
request = {
    "type": "stream",
    "to": "Denmark",
    "subject": "Castle",
    "content": "I come not, friends, to steal away your hearts."
}
result = client.send_message(request)
print(result)

# Send a private message
request = {
    "type": "private",
    "to": "scott@tqft.net",
    "content": "With mirth and laughter let old wrinkles come."
}
result = client.send_message(request)
print(result)