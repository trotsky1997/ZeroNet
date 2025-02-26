import time
import html
import os
import json
from collections import OrderedDict

from Plugin import PluginManager
from Config import config
from util import helper
from Debug import Debug
from Db import Db


@PluginManager.registerTo("UiRequest")
class UiRequestPlugin(object):

    def formatTableRow(self, row, class_name=""):
        back = []
        for format, val in row:
            if val is None:
                formatted = "n/a"
            elif format == "since":
                if val:
                    formatted = "%.0f" % (time.time() - val)
                else:
                    formatted = "n/a"
            else:
                formatted = format % val
            back.append("<td>%s</td>" % formatted)
        return "<tr class='%s'>%s</tr>" % (class_name, "".join(back))

    def getObjSize(self, obj, hpy=None):
        if hpy:
            return float(hpy.iso(obj).domisize) / 1024
        else:
            return 0

    # /Stats entry point
    @helper.encodeResponse
    def actionStats(self):
        import gc
        import sys
        from Ui import UiRequest
        from Crypt import CryptConnection
        import main


        hpy = None
        if self.get.get("size") == "1":  # Calc obj size
            try:
                import guppy
                hpy = guppy.hpy()
            except:
                pass
        self.sendHeader()

        if "Multiuser" in PluginManager.plugin_manager.plugin_names and not config.multiuser_local:
            yield "This function is disabled on this proxy"
            return

        s = time.time()

        # Style
        yield """
        <style>
         * { font-family: monospace }
         table td, table th { text-align: right; padding: 0px 10px }
         .connections td { white-space: nowrap }
         .serving-False { opacity: 0.3 }
        </style>
        """

        # Memory
        yield "rev%s | " % config.rev
        yield "%s | " % main.file_server.ip_external_list
        yield "Port: %s | " % main.file_server.port
        yield "IP Network: %s | " % main.file_server.supported_ip_types
        yield "Opened: %s | " % main.file_server.port_opened
        yield "Crypt: %s | " % CryptConnection.manager.crypt_supported
        yield "In: %.2fMB, Out: %.2fMB  | " % (
            float(main.file_server.bytes_recv) / 1024 / 1024,
            float(main.file_server.bytes_sent) / 1024 / 1024
        )
        yield "Peerid: %s  | " % main.file_server.peer_id
        yield "Time correction: %.2fs" % main.file_server.getTimecorrection()

        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem = process.get_memory_info()[0] / float(2 ** 20)
            yield "Mem: %.2fMB | " % mem
            yield "Threads: %s | " % len(process.threads())
            yield "CPU: usr %.2fs sys %.2fs | " % process.cpu_times()
            yield "Files: %s | " % len(process.open_files())
            yield "Sockets: %s | " % len(process.connections())
            yield "Calc size <a href='?size=1'>on</a> <a href='?size=0'>off</a>"
        except Exception:
            pass
        yield "<br>"

        # Connections
        yield "<b>Connections</b> (%s, total made: %s, in: %s, out: %s):<br>" % (
            len(main.file_server.connections), main.file_server.last_connection_id, main.file_server.num_incoming, main.file_server.num_outgoing
        )
        yield "<table class='connections'><tr> <th>id</th> <th>type</th> <th>ip</th> <th>open</th> <th>crypt</th> <th>ping</th>"
        yield "<th>buff</th> <th>bad</th> <th>idle</th> <th>open</th> <th>delay</th> <th>cpu</th> <th>out</th> <th>in</th> <th>last sent</th>"
        yield "<th>wait</th> <th>version</th> <th>time</th> <th>sites</th> </tr>"
        for connection in main.file_server.connections:
            if "cipher" in dir(connection.sock):
                cipher = connection.sock.cipher()[0]
                tls_version = connection.sock.version()
            else:
                cipher = connection.crypt
                tls_version = ""
            if "time" in connection.handshake and connection.last_ping_delay:
                time_correction = connection.handshake["time"] - connection.handshake_time - connection.last_ping_delay
            else:
                time_correction = 0.0
            yield self.formatTableRow([
                ("%3d", connection.id),
                ("%s", connection.type),
                ("%s:%s", (connection.ip, connection.port)),
                ("%s", connection.handshake.get("port_opened")),
                ("<span title='%s %s'>%s</span>", (cipher, tls_version, connection.crypt)),
                ("%6.3f", connection.last_ping_delay),
                ("%s", connection.incomplete_buff_recv),
                ("%s", connection.bad_actions),
                ("since", max(connection.last_send_time, connection.last_recv_time)),
                ("since", connection.start_time),
                ("%.3f", max(-1, connection.last_sent_time - connection.last_send_time)),
                ("%.3f", connection.cpu_time),
                ("%.0fk", connection.bytes_sent / 1024),
                ("%.0fk", connection.bytes_recv / 1024),
                ("<span title='Recv: %s'>%s</span>", (connection.last_cmd_recv, connection.last_cmd_sent)),
                ("%s", list(connection.waiting_requests.keys())),
                ("%s r%s", (connection.handshake.get("version"), connection.handshake.get("rev", "?"))),
                ("%.2fs", time_correction),
                ("%s", connection.sites)
            ])
        yield "</table>"

        # Trackers
        yield "<br><br><b>Trackers:</b><br>"
        yield "<table class='trackers'><tr> <th>address</th> <th>request</th> <th>successive errors</th> <th>last_request</th></tr>"
        from Site import SiteAnnouncer # importing at the top of the file breaks plugins
        for tracker_address, tracker_stat in sorted(SiteAnnouncer.global_stats.items()):
            yield self.formatTableRow([
                ("%s", tracker_address),
                ("%s", tracker_stat["num_request"]),
                ("%s", tracker_stat["num_error"]),
                ("%.0f min ago", min(999, (time.time() - tracker_stat["time_request"]) / 60))
            ])
        yield "</table>"

        if "AnnounceShare" in PluginManager.plugin_manager.plugin_names:
            yield "<br><br><b>Shared trackers:</b><br>"
            yield "<table class='trackers'><tr> <th>address</th> <th>added</th> <th>found</th> <th>latency</th> <th>successive errors</th> <th>last_success</th></tr>"
            from AnnounceShare import AnnounceSharePlugin
            for tracker_address, tracker_stat in sorted(AnnounceSharePlugin.tracker_storage.getTrackers().items()):
                yield self.formatTableRow([
                    ("%s", tracker_address),
                    ("%.0f min ago", min(999, (time.time() - tracker_stat["time_added"]) / 60)),
                    ("%.0f min ago", min(999, (time.time() - tracker_stat.get("time_found", 0)) / 60)),
                    ("%.3fs", tracker_stat["latency"]),
                    ("%s", tracker_stat["num_error"]),
                    ("%.0f min ago", min(999, (time.time() - tracker_stat["time_success"]) / 60)),
                ])
            yield "</table>"

        # Tor hidden services
        yield "<br><br><b>Tor hidden services (status: %s):</b><br>" % main.file_server.tor_manager.status
        for site_address, onion in list(main.file_server.tor_manager.site_onions.items()):
            yield "- %-34s: %s<br>" % (site_address, onion)

        # Db
        yield "<br><br><b>Db</b>:<br>"
        for db in Db.opened_dbs:
            tables = [row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
            table_rows = {}
            for table in tables:
                table_rows[table] = db.execute("SELECT COUNT(*) AS c FROM %s" % table).fetchone()["c"]
            db_size = os.path.getsize(db.db_path) / 1024.0 / 1024.0
            yield "- %.3fs: %s %.3fMB, table rows: %s<br>" % (
                time.time() - db.last_query_time, db.db_path, db_size, json.dumps(table_rows, sort_keys=True)
            )


        # Sites
        yield "<br><br><b>Sites</b>:"
        yield "<table>"
        yield "<tr><th>address</th> <th>connected</th> <th title='connected/good/total'>peers</th> <th>content.json</th> <th>out</th> <th>in</th>  </tr>"
        for site in list(self.server.sites.values()):
            yield self.formatTableRow([
                (
                    """<a href='#' onclick='document.getElementById("peers_%s").style.display="initial"; return false'>%s</a>""",
                    (site.address, site.address)
                ),
                ("%s", [peer.connection.id for peer in list(site.peers.values()) if peer.connection and peer.connection.connected]),
                ("%s/%s/%s", (
                    len([peer for peer in list(site.peers.values()) if peer.connection and peer.connection.connected]),
                    len(site.getConnectablePeers(100)),
                    len(site.peers)
                )),
                ("%s (loaded: %s)", (
                    len(site.content_manager.contents),
                    len([key for key, val in dict(site.content_manager.contents).items() if val])
                )),
                ("%.0fk", site.settings.get("bytes_sent", 0) / 1024),
                ("%.0fk", site.settings.get("bytes_recv", 0) / 1024),
            ], "serving-%s" % site.settings["serving"])
            yield "<tr><td id='peers_%s' style='display: none; white-space: pre' colspan=6>" % site.address
            for key, peer in list(site.peers.items()):
                if peer.time_found:
                    time_found = int(time.time() - peer.time_found) / 60
                else:
                    time_found = "--"
                if peer.connection:
                    connection_id = peer.connection.id
                else:
                    connection_id = None
                if site.content_manager.has_optional_files:
                    yield "Optional files: %4s " % len(peer.hashfield)
                time_added = (time.time() - peer.time_added) / (60 * 60 * 24)
                yield "(#%4s, rep: %2s, err: %s, found: %3s min, add: %.1f day) %30s -<br>" % (connection_id, peer.reputation, peer.connection_error, time_found, time_added, key)
            yield "<br></td></tr>"
        yield "</table>"

        # Big files
        yield "<br><br><b>Big files</b>:<br>"
        for site in list(self.server.sites.values()):
            if not site.settings.get("has_bigfile"):
                continue
            bigfiles = {}
            yield """<a href="#" onclick='document.getElementById("bigfiles_%s").style.display="initial"; return false'>%s</a><br>""" % (site.address, site.address)
            for peer in list(site.peers.values()):
                if not peer.time_piecefields_updated:
                    continue
                for sha512, piecefield in peer.piecefields.items():
                    if sha512 not in bigfiles:
                        bigfiles[sha512] = []
                    bigfiles[sha512].append(peer)

            yield "<div id='bigfiles_%s' style='display: none'>" % site.address
            for sha512, peers in bigfiles.items():
                yield "<br> - " + sha512 + " (hash id: %s)<br>" % site.content_manager.hashfield.getHashId(sha512)
                yield "<table>"
                for peer in peers:
                    yield "<tr><td>" + peer.key + "</td><td>" + peer.piecefields[sha512].tostring() + "</td></tr>"
                yield "</table>"
            yield "</div>"

        # Cmd stats
        yield "<div style='float: left'>"
        yield "<br><br><b>Sent commands</b>:<br>"
        yield "<table>"
        for stat_key, stat in sorted(main.file_server.stat_sent.items(), key=lambda i: i[1]["bytes"], reverse=True):
            yield "<tr><td>%s</td><td style='white-space: nowrap'>x %s =</td><td>%.0fkB</td></tr>" % (stat_key, stat["num"], stat["bytes"] / 1024)
        yield "</table>"
        yield "</div>"

        yield "<div style='float: left; margin-left: 20%; max-width: 50%'>"
        yield "<br><br><b>Received commands</b>:<br>"
        yield "<table>"
        for stat_key, stat in sorted(main.file_server.stat_recv.items(), key=lambda i: i[1]["bytes"], reverse=True):
            yield "<tr><td>%s</td><td style='white-space: nowrap'>x %s =</td><td>%.0fkB</td></tr>" % (stat_key, stat["num"], stat["bytes"] / 1024)
        yield "</table>"
        yield "</div>"
        yield "<div style='clear: both'></div>"

        # No more if not in debug mode
        if not config.debug:
            return

        # Object types

        obj_count = {}
        for obj in gc.get_objects():
            obj_type = str(type(obj))
            if obj_type not in obj_count:
                obj_count[obj_type] = [0, 0]
            obj_count[obj_type][0] += 1  # Count
            obj_count[obj_type][1] += float(sys.getsizeof(obj)) / 1024  # Size

        yield "<br><br><b>Objects in memory (types: %s, total: %s, %.2fkb):</b><br>" % (
            len(obj_count),
            sum([stat[0] for stat in list(obj_count.values())]),
            sum([stat[1] for stat in list(obj_count.values())])
        )

        for obj, stat in sorted(list(obj_count.items()), key=lambda x: x[1][0], reverse=True):  # Sorted by count
            yield " - %.1fkb = %s x <a href=\"/Listobj?type=%s\">%s</a><br>" % (stat[1], stat[0], obj, html.escape(obj))

        # Classes

        class_count = {}
        for obj in gc.get_objects():
            obj_type = str(type(obj))
            if obj_type != "<type 'instance'>":
                continue
            class_name = obj.__class__.__name__
            if class_name not in class_count:
                class_count[class_name] = [0, 0]
            class_count[class_name][0] += 1  # Count
            class_count[class_name][1] += float(sys.getsizeof(obj)) / 1024  # Size

        yield "<br><br><b>Classes in memory (types: %s, total: %s, %.2fkb):</b><br>" % (
            len(class_count),
            sum([stat[0] for stat in list(class_count.values())]),
            sum([stat[1] for stat in list(class_count.values())])
        )

        for obj, stat in sorted(list(class_count.items()), key=lambda x: x[1][0], reverse=True):  # Sorted by count
            yield " - %.1fkb = %s x <a href=\"/Dumpobj?class=%s\">%s</a><br>" % (stat[1], stat[0], obj, html.escape(obj))

        from greenlet import greenlet
        objs = [obj for obj in gc.get_objects() if isinstance(obj, greenlet)]
        yield "<br>Greenlets (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj)))

        from Worker import Worker
        objs = [obj for obj in gc.get_objects() if isinstance(obj, Worker)]
        yield "<br>Workers (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj)))

        from Connection import Connection
        objs = [obj for obj in gc.get_objects() if isinstance(obj, Connection)]
        yield "<br>Connections (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj)))

        from socket import socket
        objs = [obj for obj in gc.get_objects() if isinstance(obj, socket)]
        yield "<br>Sockets (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj)))

        from msgpack import Unpacker
        objs = [obj for obj in gc.get_objects() if isinstance(obj, Unpacker)]
        yield "<br>Msgpack unpacker (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj)))

        from Site.Site import Site
        objs = [obj for obj in gc.get_objects() if isinstance(obj, Site)]
        yield "<br>Sites (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj)))

        objs = [obj for obj in gc.get_objects() if isinstance(obj, self.server.log.__class__)]
        yield "<br>Loggers (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj.name)))

        objs = [obj for obj in gc.get_objects() if isinstance(obj, UiRequest)]
        yield "<br>UiRequests (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj)))

        from Peer import Peer
        objs = [obj for obj in gc.get_objects() if isinstance(obj, Peer)]
        yield "<br>Peers (%s):<br>" % len(objs)
        for obj in objs:
            yield " - %.1fkb: %s<br>" % (self.getObjSize(obj, hpy), html.escape(repr(obj)))

        objs = [(key, val) for key, val in sys.modules.items() if val is not None]
        objs.sort()
        yield "<br>Modules (%s):<br>" % len(objs)
        for module_name, module in objs:
            yield " - %.3fkb: %s %s<br>" % (self.getObjSize(module, hpy), module_name, html.escape(repr(module)))

        gc.collect()  # Implicit grabage collection
        yield "Done in %.1f" % (time.time() - s)

    def actionDumpobj(self):

        import gc
        import sys

        self.sendHeader()

        if "Multiuser" in PluginManager.plugin_manager.plugin_names and not config.multiuser_local:
            yield "This function is disabled on this proxy"
            return

        # No more if not in debug mode
        if not config.debug:
            yield "Not in debug mode"
            return

        class_filter = self.get.get("class")

        yield """
        <style>
         * { font-family: monospace; white-space: pre }
         table * { text-align: right; padding: 0px 10px }
        </style>
        """

        objs = gc.get_objects()
        for obj in objs:
            obj_type = str(type(obj))
            if obj_type != "<type 'instance'>" or obj.__class__.__name__ != class_filter:
                continue
            yield "%.1fkb %s... " % (float(sys.getsizeof(obj)) / 1024, html.escape(str(obj)))
            for attr in dir(obj):
                yield "- %s: %s<br>" % (attr, html.escape(str(getattr(obj, attr))))
            yield "<br>"

        gc.collect()  # Implicit grabage collection

    def actionListobj(self):

        import gc
        import sys

        self.sendHeader()

        if "Multiuser" in PluginManager.plugin_manager.plugin_names and not config.multiuser_local:
            yield "This function is disabled on this proxy"
            return

        # No more if not in debug mode
        if not config.debug:
            yield "Not in debug mode"
            return

        type_filter = self.get.get("type")

        yield """
        <style>
         * { font-family: monospace; white-space: pre }
         table * { text-align: right; padding: 0px 10px }
        </style>
        """

        yield "Listing all %s objects in memory...<br>" % html.escape(type_filter)

        ref_count = {}
        objs = gc.get_objects()
        for obj in objs:
            obj_type = str(type(obj))
            if obj_type != type_filter:
                continue
            refs = [
                ref for ref in gc.get_referrers(obj)
                if hasattr(ref, "__class__") and
                ref.__class__.__name__ not in ["list", "dict", "function", "type", "frame", "WeakSet", "tuple"]
            ]
            if not refs:
                continue
            try:
                yield "%.1fkb <span title=\"%s\">%s</span>... " % (
                    float(sys.getsizeof(obj)) / 1024, html.escape(str(obj)), html.escape(str(obj)[0:100].ljust(100))
                )
            except:
                continue
            for ref in refs:
                yield " ["
                if "object at" in str(ref) or len(str(ref)) > 100:
                    yield str(ref.__class__.__name__)
                else:
                    yield str(ref.__class__.__name__) + ":" + html.escape(str(ref))
                yield "] "
                ref_type = ref.__class__.__name__
                if ref_type not in ref_count:
                    ref_count[ref_type] = [0, 0]
                ref_count[ref_type][0] += 1  # Count
                ref_count[ref_type][1] += float(sys.getsizeof(obj)) / 1024  # Size
            yield "<br>"

        yield "<br>Object referrer (total: %s, %.2fkb):<br>" % (len(ref_count), sum([stat[1] for stat in list(ref_count.values())]))

        for obj, stat in sorted(list(ref_count.items()), key=lambda x: x[1][0], reverse=True)[0:30]:  # Sorted by count
            yield " - %.1fkb = %s x %s<br>" % (stat[1], stat[0], html.escape(str(obj)))

        gc.collect()  # Implicit grabage collection

    @helper.encodeResponse
    def actionBenchmark(self):
        import sys
        import gc
        from contextlib import contextmanager

        output = self.sendHeader()

        if "Multiuser" in PluginManager.plugin_manager.plugin_names and not config.multiuser_local:
            yield "This function is disabled on this proxy"
            return

        @contextmanager
        def benchmark(name, standard):
            self.log.debug("Benchmark: %s" % name)
            s = time.time()
            output(b"- %s" % name.encode())
            try:
                yield 1
            except Exception as err:
                self.log.exception(err)
                output(b"<br><b>! Error: %s</b><br>" % Debug.formatException(err).encode())
            taken = time.time() - s
            if taken > 0:
                multipler = standard / taken
            else:
                multipler = 99
            if multipler < 0.3:
                speed = "Sloooow"
            elif multipler < 0.5:
                speed = "Ehh"
            elif multipler < 0.8:
                speed = "Goodish"
            elif multipler < 1.2:
                speed = "OK"
            elif multipler < 1.7:
                speed = "Fine"
            elif multipler < 2.5:
                speed = "Fast"
            elif multipler < 3.5:
                speed = "WOW"
            else:
                speed = "Insane!!"
            output(b"%.3fs [x%.2f: %s]<br>" % (taken, multipler, speed.encode()))
            time.sleep(0.01)

        yield """
        <style>
         * { font-family: monospace }
         table * { text-align: right; padding: 0px 10px }
        </style>
        """

        yield "Benchmarking ZeroNet %s (rev%s) Python %s on: %s...<br>" % (config.version, config.rev, sys.version, sys.platform)

        t = time.time()

        # CryptBitcoin
        yield "<br>CryptBitcoin:<br>"
        from Crypt import CryptBitcoin

        # seed = CryptBitcoin.newSeed()
        # yield "- Seed: %s<br>" % seed
        seed = "e180efa477c63b0f2757eac7b1cce781877177fe0966be62754ffd4c8592ce38"

        with benchmark("hdPrivatekey x 10", 0.7):
            for i in range(10):
                privatekey = CryptBitcoin.hdPrivatekey(seed, i * 10)
                yield "."
            valid = "5JsunC55XGVqFQj5kPGK4MWgTL26jKbnPhjnmchSNPo75XXCwtk"
            assert privatekey == valid, "%s != %s" % (privatekey, valid)

        data = "Hello" * 1024  # 5k
        with benchmark("sign x 10", 0.35):
            for i in range(10):
                yield "."
                sign = CryptBitcoin.sign(data, privatekey)
            valid = "G1GXaDauZ8vX/N9Jn+MRiGm9h+I94zUhDnNYFaqMGuOiBHB+kp4cRPZOL7l1yqK5BHa6J+W97bMjvTXtxzljp6w="
            assert sign == valid, "%s != %s" % (sign, valid)

        address = CryptBitcoin.privatekeyToAddress(privatekey)
        for lib_verify in ["btctools", "openssl", "libsecp256k1"]:
            try:
                CryptBitcoin.loadLib(lib_verify)
                loaded = True
            except Exception as err:
                yield "- Error loading %s: %s<br>" % (lib_verify, err)
                loaded = False
            if not loaded:
                continue
            with benchmark("%s verify x 100" % lib_verify, 0.37):
                for i in range(100):
                    if i % 10 == 0:
                        yield "."
                    ok = CryptBitcoin.verify(data, address, sign, lib_verify=lib_verify)
                assert ok, "does not verify from %s" % address

        # CryptHash
        yield "<br>CryptHash:<br>"
        from Crypt import CryptHash
        import io

        data = io.BytesIO(b"Hello" * 1024 * 1024)  # 5m
        with benchmark("sha256 5M x 10", 0.6):
            for i in range(10):
                data.seek(0)
                hash = CryptHash.sha256sum(data)
                yield "."
            valid = "8cd629d9d6aff6590da8b80782a5046d2673d5917b99d5603c3dcb4005c45ffa"
            assert hash == valid, "%s != %s" % (hash, valid)

        data = io.BytesIO(b"Hello" * 1024 * 1024)  # 5m
        with benchmark("sha512 5M x 10", 0.6):
            for i in range(10):
                data.seek(0)
                hash = CryptHash.sha512sum(data)
                yield "."
            valid = "9ca7e855d430964d5b55b114e95c6bbb114a6d478f6485df93044d87b108904d"
            assert hash == valid, "%s != %s" % (hash, valid)

        with benchmark("os.urandom(256) x 1000", 0.0065):
            for i in range(10):
                for y in range(100):
                    data = os.urandom(256)
                yield "."

        # Msgpack
        from util import Msgpack
        yield "<br>Msgpack: (version: %s)<br>" % ".".join(map(str, Msgpack.msgpack.version))
        binary = b'fqv\xf0\x1a"e\x10,\xbe\x9cT\x9e(\xa5]u\x072C\x8c\x15\xa2\xa8\x93Sw)\x19\x02\xdd\t\xfb\xf67\x88\xd9\xee\x86\xa1\xe4\xb6,\xc6\x14\xbb\xd7$z\x1d\xb2\xda\x85\xf5\xa0\x97^\x01*\xaf\xd3\xb0!\xb7\x9d\xea\x89\xbbh8\xa1"\xa7]e(@\xa2\xa5g\xb7[\xae\x8eE\xc2\x9fL\xb6s\x19\x19\r\xc8\x04S\xd0N\xe4]?/\x01\xea\xf6\xec\xd1\xb3\xc2\x91\x86\xd7\xf4K\xdf\xc2lV\xf4\xe8\x80\xfc\x8ep\xbb\x82\xb3\x86\x98F\x1c\xecS\xc8\x15\xcf\xdc\xf1\xed\xfc\xd8\x18r\xf9\x80\x0f\xfa\x8cO\x97(\x0b]\xf1\xdd\r\xe7\xbf\xed\x06\xbd\x1b?\xc5\xa0\xd7a\x82\xf3\xa8\xe6@\xf3\ri\xa1\xb10\xf6\xd4W\xbc\x86\x1a\xbb\xfd\x94!bS\xdb\xaeM\x92\x00#\x0b\xf7\xad\xe9\xc2\x8e\x86\xbfi![%\xd31]\xc6\xfc2\xc9\xda\xc6v\x82P\xcc\xa9\xea\xb9\xff\xf6\xc8\x17iD\xcf\xf3\xeeI\x04\xe9\xa1\x19\xbb\x01\x92\xf5nn4K\xf8\xbb\xc6\x17e>\xa7 \xbbv'
        data = OrderedDict(
            sorted({"int": 1024 * 1024 * 1024, "float": 12345.67890, "text": "hello" * 1024, "binary": binary}.items())
        )
        data_packed_valid = b'\x84\xa6binary\xc5\x01\x00fqv\xf0\x1a"e\x10,\xbe\x9cT\x9e(\xa5]u\x072C\x8c\x15\xa2\xa8\x93Sw)\x19\x02\xdd\t\xfb\xf67\x88\xd9\xee\x86\xa1\xe4\xb6,\xc6\x14\xbb\xd7$z\x1d\xb2\xda\x85\xf5\xa0\x97^\x01*\xaf\xd3\xb0!\xb7\x9d\xea\x89\xbbh8\xa1"\xa7]e(@\xa2\xa5g\xb7[\xae\x8eE\xc2\x9fL\xb6s\x19\x19\r\xc8\x04S\xd0N\xe4]?/\x01\xea\xf6\xec\xd1\xb3\xc2\x91\x86\xd7\xf4K\xdf\xc2lV\xf4\xe8\x80\xfc\x8ep\xbb\x82\xb3\x86\x98F\x1c\xecS\xc8\x15\xcf\xdc\xf1\xed\xfc\xd8\x18r\xf9\x80\x0f\xfa\x8cO\x97(\x0b]\xf1\xdd\r\xe7\xbf\xed\x06\xbd\x1b?\xc5\xa0\xd7a\x82\xf3\xa8\xe6@\xf3\ri\xa1\xb10\xf6\xd4W\xbc\x86\x1a\xbb\xfd\x94!bS\xdb\xaeM\x92\x00#\x0b\xf7\xad\xe9\xc2\x8e\x86\xbfi![%\xd31]\xc6\xfc2\xc9\xda\xc6v\x82P\xcc\xa9\xea\xb9\xff\xf6\xc8\x17iD\xcf\xf3\xeeI\x04\xe9\xa1\x19\xbb\x01\x92\xf5nn4K\xf8\xbb\xc6\x17e>\xa7 \xbbv\xa5float\xcb@\xc8\x1c\xd6\xe61\xf8\xa1\xa3int\xce@\x00\x00\x00\xa4text\xda\x14\x00hellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohellohello'
        with benchmark("pack 5K x 10 000", 0.78):
            for i in range(10):
                for y in range(1000):
                    data_packed = Msgpack.pack(data)
                yield "."
            assert data_packed == data_packed_valid, "%s<br>!=<br>%s" % (repr(data_packed), repr(data_packed_valid))

        with benchmark("unpack 5K x 10 000", 1.2):
            for i in range(10):
                for y in range(1000):
                    data_unpacked = Msgpack.unpack(data_packed, decode=False)
                yield "."
            assert data == data_unpacked, "%s != %s" % (data_unpacked, data)

        for fallback in [True, False]:
            with benchmark("streaming unpack 5K x 10 000 (fallback: %s)" % fallback, 1.4):
                for i in range(10):
                    unpacker = Msgpack.getUnpacker(decode=False, fallback=fallback)
                    for y in range(1000):
                        unpacker.feed(data_packed)
                        for data_unpacked in unpacker:
                            pass
                    yield "."
                assert data == data_unpacked, "%s != %s" % (data_unpacked, data)

        # Db
        import sqlite3
        yield "<br>Db: (version: %s, API: %s)<br>" % (sqlite3.sqlite_version, sqlite3.version)

        schema = {
            "db_name": "TestDb",
            "db_file": "%s/benchmark.db" % config.data_dir,
            "maps": {
                ".*": {
                    "to_table": {
                        "test": "test"
                    }
                }
            },
            "tables": {
                "test": {
                    "cols": [
                        ["test_id", "INTEGER"],
                        ["title", "TEXT"],
                        ["json_id", "INTEGER REFERENCES json (json_id)"]
                    ],
                    "indexes": ["CREATE UNIQUE INDEX test_key ON test(test_id, json_id)"],
                    "schema_changed": 1426195822
                }
            }
        }

        if os.path.isfile("%s/benchmark.db" % config.data_dir):
            os.unlink("%s/benchmark.db" % config.data_dir)

        with benchmark("Open x 10", 0.13):
            for i in range(10):
                db = Db.Db(schema, "%s/benchmark.db" % config.data_dir)
                db.checkTables()
                db.close()
                yield "."

        db = Db.Db(schema, "%s/benchmark.db" % config.data_dir)
        db.checkTables()
        import json

        with benchmark("Insert x 10 x 1000", 1.0):
            for u in range(10):  # 10 user
                data = {"test": []}
                for i in range(1000):  # 1000 line of data
                    data["test"].append({"test_id": i, "title": "Testdata for %s message %s" % (u, i)})
                json.dump(data, open("%s/test_%s.json" % (config.data_dir, u), "w"))
                db.updateJson("%s/test_%s.json" % (config.data_dir, u))
                os.unlink("%s/test_%s.json" % (config.data_dir, u))
                yield "."

        with benchmark("Buffered insert x 100 x 100", 1.3):
            cur = db.getCursor()
            cur.logging = False
            for u in range(100, 200):  # 100 user
                data = {"test": []}
                for i in range(100):  # 1000 line of data
                    data["test"].append({"test_id": i, "title": "Testdata for %s message %s" % (u, i)})
                json.dump(data, open("%s/test_%s.json" % (config.data_dir, u), "w"))
                db.updateJson("%s/test_%s.json" % (config.data_dir, u), cur=cur)
                os.unlink("%s/test_%s.json" % (config.data_dir, u))
                if u % 10 == 0:
                    yield "."

        yield " - Total rows in db: %s<br>" % db.execute("SELECT COUNT(*) AS num FROM test").fetchone()[0]

        with benchmark("Indexed query x 1000", 0.25):
            found = 0
            cur = db.getCursor()
            cur.logging = False
            for i in range(1000):  # 1000x by test_id
                res = cur.execute("SELECT * FROM test WHERE test_id = %s" % i)
                for row in res:
                    found += 1
                if i % 100 == 0:
                    yield "."

            assert found == 20000, "Found: %s != 20000" % found

        with benchmark("Not indexed query x 100", 0.6):
            found = 0
            cur = db.getCursor()
            cur.logging = False
            for i in range(100):  # 1000x by test_id
                res = cur.execute("SELECT * FROM test WHERE json_id = %s" % i)
                for row in res:
                    found += 1
                if i % 10 == 0:
                    yield "."

            assert found == 18900, "Found: %s != 18900" % found

        with benchmark("Like query x 100", 1.8):
            found = 0
            cur = db.getCursor()
            cur.logging = False
            for i in range(100):  # 1000x by test_id
                res = cur.execute("SELECT * FROM test WHERE title LIKE '%%message %s%%'" % i)
                for row in res:
                    found += 1
                if i % 10 == 0:
                    yield "."

            assert found == 38900, "Found: %s != 11000" % found

        db.close()
        if os.path.isfile("%s/benchmark.db" % config.data_dir):
            os.unlink("%s/benchmark.db" % config.data_dir)

        gc.collect()  # Implicit grabage collection

        # Zip
        yield "<br>Compression:<br>"
        import zipfile
        test_data = b"Test" * 1024
        file_name = b"\xc3\x81rv\xc3\xadzt\xc5\xb0r\xc5\x91t\xc3\xbck\xc3\xb6r\xc3\xb3g\xc3\xa9p\xe4\xb8\xad\xe5\x8d\x8e%s.txt".decode("utf8")

        with benchmark("Zip pack x 10", 0.12):
            for i in range(10):
                with zipfile.ZipFile('%s/test.zip' % config.data_dir, 'w') as archive:
                    for y in range(100):
                        zip_info = zipfile.ZipInfo(file_name % y, (1980,1,1,0,0,0))
                        zip_info.compress_type = zipfile.ZIP_DEFLATED
                        zip_info.create_system = 3
                        zip_info.flag_bits = 0
                        zip_info.external_attr = 25165824
                        archive.writestr(zip_info, test_data)
                yield "."

            hash = CryptHash.sha512sum(open("%s/test.zip" % config.data_dir, "rb"))
            valid = "f630fece29fff1cc8dbf454e47a87fea2746a4dbbd2ceec098afebab45301562"
            assert hash == valid, "Invalid hash: %s != %s<br>" % (hash, valid)

        with benchmark("Zip unpack x 10", 0.2):
            for i in range(10):
                with zipfile.ZipFile('%s/test.zip' % config.data_dir) as archive:
                    for y in range(100):
                        data = archive.open(file_name % y).read()
                        assert archive.open(file_name % y).read() == test_data, "Invalid data: %s..." % data[0:30]
                yield "."

        if os.path.isfile("%s/test.zip" % config.data_dir):
            os.unlink("%s/test.zip" % config.data_dir)

        # gz, bz2, xz
        import tarfile
        import gzip

        # Monkey patch _init_write_gz to use fixed date in order to keep the hash independent from datetime
        def nodate_write_gzip_header(self):
            self._write_mtime = 0
            original_write_gzip_header(self)

        original_write_gzip_header = gzip.GzipFile._write_gzip_header
        gzip.GzipFile._write_gzip_header = nodate_write_gzip_header

        test_data_io = io.BytesIO(b"Test" * 1024)
        archive_formats = {
            "gz": {"hash": "4704ebd8c987ed6f833059f1de9c475d443b0539b8d4c4cb8b49b26f7bbf2d19", "time_pack": 0.3, "time_unpack": 0.2},
            "bz2": {"hash": "90cba0b4d9abaa37b830bf37e4adba93bfd183e095b489ebee62aaa94339f3b5", "time_pack": 2.0, "time_unpack": 0.5},
            "xz": {"hash": "37abc16d552cfd4a495cb2acbf8b1d5877631d084f6571f4d6544bc548c69bae", "time_pack": 1.4, "time_unpack": 0.2}
        }
        for ext, format_data in archive_formats.items():
            archive_path = '%s/test.tar.%s' % (config.data_dir, ext)
            with benchmark("Tar.%s pack x 10" % ext, format_data["time_pack"]):
                for i in range(10):
                    with tarfile.open(archive_path, 'w:%s' % ext) as archive:
                        for y in range(100):
                            test_data_io.seek(0)
                            tar_info = tarfile.TarInfo(file_name % y)
                            tar_info.size = 4 * 1024
                            archive.addfile(tar_info, test_data_io)
                    yield "."

                hash = CryptHash.sha512sum(open("%s/test.tar.%s" % (config.data_dir, ext), "rb"))
                valid = format_data["hash"]
                assert hash == valid, "Invalid hash: %s != %s<br>" % (hash, valid)

            archive_size = os.path.getsize(archive_path) / 1024
            with benchmark("Tar.%s unpack (%.2fkB) x 10" % (ext, archive_size), format_data["time_unpack"]):
                for i in range(10):
                    with tarfile.open(archive_path, 'r:%s' % ext) as archive:
                        for y in range(100):
                            assert archive.extractfile(file_name % y).read() == test_data
                    yield "."

            if os.path.isfile(archive_path):
                os.unlink(archive_path)

        yield "<br>Done. Total: %.2fs" % (time.time() - t)

    def actionGcCollect(self):
        import gc
        self.sendHeader()
        yield str(gc.collect())
