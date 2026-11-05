import socket
from protocol import send_header, recv_header

class FileClient:
    def __init__(self, host, port, name):
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(host, port)

    def request(self, header):
        return

    def hello(self):
        return self.request({"cmd": "HELLO", "name": self.name})

    def list_dir(self):
        TODO: make

    def close(self):
        TODO: make

def main():
    client = FileClient("127.0.0.1", 5050, "carson")
    print(client.hello())
    print(client.list_dir())
    client.close()

if __name__ == "__main__":
    main()