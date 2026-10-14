"""Start a loopback-only server and open the local UI."""
import argparse
import socket
import threading
import webbrowser
import uvicorn

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Clean Local')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    # Fail clearly rather than opening an unrelated service on an occupied port.
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1',args.port))
        except OSError:
            parser.exit(1,f'Port {args.port} is busy. Close the previous instance or use --port 8766.\n')
    url=f'http://127.0.0.1:{args.port}'
    print(f'Clean Local: {url}\nKeep this terminal open. Ctrl+C to stop.')
    if not args.no_browser:
        threading.Timer(1.5,lambda:webbrowser.open(url)).start()
    uvicorn.run('app.main:app',host='127.0.0.1',port=args.port,log_level='info',workers=1)
