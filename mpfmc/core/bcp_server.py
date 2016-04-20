"""BCP Server interface for the MPF Media Controller"""

import logging
import queue
import socket
import sys
import threading
import time
import traceback

import mpf.core.bcp as bcp


class BCPServer(threading.Thread):
    """Parent class for the BCP Server thread.

    Args:
        mc: A reference to the main MediaController instance.
        receiving_queue: A shared Queue() object which holds incoming BCP
            commands.
        sending_queue: A shared Queue() object which holds outgoing BCP
            commands.

    """

    def __init__(self, mc, receiving_queue, sending_queue):

        threading.Thread.__init__(self)
        self.mc = mc
        self.log = logging.getLogger('BCP')
        self.receive_queue = receiving_queue
        self.sending_queue = sending_queue
        self.connection = None
        self.socket = None
        self.done = False

        self.setup_server_socket()
        self.sending_thread = threading.Thread(target=self.sending_loop)
        self.sending_thread.daemon = True
        self.sending_thread.start()

    def setup_server_socket(self, interface='localhost', port=5050):
        """Sets up the socket listener.

        Args:
            interface: String name of which interface this socket will listen
                on.
            port: Integer TCP port number the socket will listen on.

        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.log.info('Starting up on %s port %s', interface, port)

        try:
            self.socket.bind((interface, port))
        except IOError:
            self.log.critical('Socket bind IOError')
            raise

        self.socket.listen(1)
        self.socket.settimeout(1)

    def run(self):
        """The socket thread's run loop."""

        try:
            while True:
                self.log.info("Waiting for a connection...")
                self.mc.events.post('client_disconnected',
                                    host=self.socket.getsockname()[0],
                                    port=self.socket.getsockname()[1])
                self.mc.bcp_client_connected = False

                while not self.connection:
                    try:
                        self.connection, client_address = self.socket.accept()
                    except socket.timeout:
                        if self.mc.thread_stopper.is_set():
                            print("Stopping BCP listener thread")
                            self.socket.shutdown(socket.SHUT_RDWR)
                            self.socket.close()
                            return

                self.log.info("Received connection from: %s:%s",
                              client_address[0], client_address[1])
                self.mc.events.post('client_connected',
                                    address=client_address[0],
                                    port=client_address[1])
                self.mc.bcp_client_connected = True

                # Receive the data in small chunks and retransmit it
                while not self.mc.thread_stopper.is_set():
                    try:
                        socket_chars = self.connection.recv(4096).decode(
                            'utf-8')
                        if socket_chars:
                            commands = socket_chars.split("\n")
                            for cmd in commands:
                                if cmd:
                                    self.process_received_message(cmd)
                        else:
                            # no more data
                            break

                    except socket.timeout:
                        pass

                    except OSError:
                        if self.mc.machine_config['mpf-mc'][
                                'exit_on_disconnect']:
                            self.mc.stop()
                        else:
                            break

        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value,
                                               exc_traceback)
            msg = ''.join(line for line in lines)
            self.mc.crash_queue.put(msg)

    def stop(self):
        """ Stops and shuts down the BCP server."""
        if not self.done:
            self.log.info("Socket thread stopping.")
            self.sending_queue.put('goodbye', None)
            time.sleep(1)  # give it a chance to send goodbye before quitting
            self.done = True
            self.mc.done = True

    def sending_loop(self):
        """Sending loop which transmits data from the sending queue to the
        remote socket.

        This method is run as a thread.
        """
        try:
            while not self.done:
                try:
                    msg, rawbytes = self.sending_queue.get(block=True,
                                                           timeout=1)

                except queue.Empty:
                    if self.mc.thread_stopper.is_set():
                        print("Stopping BCP sending thread")
                        self.socket.shutdown(socket.SHUT_RDWR)
                        self.socket.close()
                        self.socket = None
                        self.mc.socket_thread_stopped()
                        return

                    else:
                        continue

                if not rawbytes:
                    self.connection.sendall(('{}\n'.format(msg)).encode('utf-8'))

                else:
                    self.connection.sendall('{}&bytes={}\n'.format(
                        msg, len(rawbytes)).encode('utf-8'))
                    self.connection.sendall(rawbytes)

        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(exc_type, exc_value,
                                               exc_traceback)
            msg = ''.join(line for line in lines)
            self.mc.crash_queue.put(msg)

            # todo this does not crash mpf-mc

    def process_received_message(self, message):
        """Puts a received BCP message into the receiving queue.

        Args:
            message: The incoming BCP message

        """
        self.log.debug('Received "%s"', message)
        cmd, kwargs = bcp.decode_command_string(message)
        self.receive_queue.put((cmd, kwargs))
