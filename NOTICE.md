# Open-source references

This project is an independent interoperability implementation. The protocol
behavior and file layouts were cross-checked against these public projects:

- PKHeX / PKHeX.Core by kwsch and contributors (GPL-3.0), especially the PGF,
  PCD, PGT, and PK4 data structures.
- MysteryGiftConvert by AdmiralCurtiss (MIT), for the Gen-IV/Gen-V DLS wrapper
  layout and CRC-16/CCITT parameters.
- IR-GTS by JamieJQuinn and contributors (GPL-3.0), for documented Generation-IV
  GTS endpoint behavior.
- dwc_network_server_emulator by barronwaffles and contributors (AGPL-3.0), for
  the Nintendo DLS `count` / `list` / `contents` request flow.

No Nintendo ROM, official event payload, certificate, private key, or copyrighted
game asset is included. Pokémon and Nintendo DS are trademarks of their respective
owners. Use only with games and hardware you are authorized to operate.
