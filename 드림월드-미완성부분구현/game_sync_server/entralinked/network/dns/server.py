#!/usr/bin/env python3
import logging
from dnslib import RR, A, QTYPE
from dnslib.server import DNSServer, BaseResolver, DNSRecord

logger = logging.getLogger(__name__)

class FixedResolver(BaseResolver):
    def __init__(self, host_address: str):
        self.host_address = host_address

    def resolve(self, request: DNSRecord, handler):
        reply = request.reply()
        qname = request.q.qname
        qtype = request.q.qtype

        if qtype == QTYPE.A:
            reply.add_answer(RR(qname, QTYPE.A, rdata=A(self.host_address), ttl=0))
        else:
            logger.warning(f"Unsupported record type in DNS question: {qtype}")

        return reply

class DnsServer:
    def __init__(self, host_address: str):
        self.host_address = host_address
        self.server = None

    def start(self):
        if self.server:
            return True
        logger.info("Starting DNS server...")
        # Bind only to the address advertised to the DS.  Binding 0.0.0.0 on
        # Windows can silently share UDP/53 with Internet Connection Sharing,
        # causing DNS packets to be delivered intermittently to the wrong
        # resolver and surfacing as a generic communication error on the DS.
        self.server = DNSServer(
            FixedResolver(self.host_address),
            address=self.host_address,
            port=53,
        )
        self.server.start_thread()
        logger.info(f"DNS server listening @ {self.host_address}:53")
        return True

    def stop(self):
        if not self.server:
            return True
        logger.info("Stopping DNS server...")
        self.server.stop()
        self.server = None
        return True
