#!/usr/bin/env python3
# Copyright © 2015 Andrew Wilcox and Elizabeth Myers.
# All rights reserved.
# This file is part of the PyIRC 3 project. See LICENSE in the root directory
# for licensing information.


"""Track IRC ban modes (+beIq)

In order to be taught about new types, this extension must know the numerics
used for ban listing.
"""


from time import time
from collections import namedtuple, defaultdict
from logging import getLogger

from PyIRC.extension import BaseExtension
from PyIRC.hook import hook, PRIORITY_LAST
from PyIRC.auxparse import mode_parse, prefix_parse
from PyIRC.line import Hostmask
from PyIRC.numerics import Numerics


logger = getLogger(__name__)


BanEntry = namedtuple("BanEntry", "string setter timestamp")


class BanTrack(BaseExtension):

    """Track bans and other "list" modes.

    This supports +beI, Inspircd +g, and Charybdis-style +q. Others may be
    added for other IRC daemons in the future.

    .. note::
        Unless you are opped, your view of modes such as +eI may be limited
        and incomplete.
    """

    requires = ["ISupport", "ChannelTrack", "BasicRFC"]

    default_ban_numerics_modes = {
        Numerics.RPL_BANLIST.value : 'b',
        Numerics.RPL_EXCEPTLIST.value : 'e',
        Numerics.RPL_INVITELIST.value : 'I',
        Numerics.RPL_QUIETLIST.value : 'q',
    }

    def __init__(self, base, **kwargs):

        """Arguments:

        ban_numerics_modes
            A mapping of numerics to modes, useful on InspIRCd servers
            A sensible default is used.
        """
        self.base = base

        # Numerics to modes
        self.ban_numerics_modes = kwargs.get('ban_numerics_modes',
                                             self.default_ban_numerics_modes)

    @hook("commands", "JOIN", PRIORITY_LAST)
    def join(self, event):
        logger.debug("Creating ban modes for channel %s",
                     event.line.params[0])
        channeltrack = self.get_extension("ChannelTrack")
        channel = channeltrack.get_channel(event.line.params[0])
        channel.ban_modes = defaultdict(list)

    @hook("commands", "MODE")
    def mode(self, event):
        setter = event.line.hostmask
        params = event.line.params
        modes = params[1]
        modeparams = params[2:]

        channeltrack = self.get_extension("ChannelTrack")
        channel = channeltrack.get_channel(event.line.params[0])
        if not channel:
            # Not a channel or we don't know about it.
            return

        ban_modes = channel.ban_modes

        isupport = self.get_extension("ISupport")
        modegroups = isupport.get("CHANMODES")
        prefixes = prefix_parse(isupport.get("PREFIX"))

        send_request = False
        for (mode, param, adding) in mode_parse(modes, modeparams, modegroups,
                                                prefixes):
            if param is None:
                # Don't care.
                continue

            if mode in prefixes and mode != 'v':
                # Send a modes request if it's us
                if not (send_request ^ adding):
                    # No need to check
                    continue

                basicrfc = self.get_extension("BasicRFC")
                if self.casefold(param) == self.casefold(basicrfc.nick):
                    # Adjust flag
                    send_request = adding

            if mode not in modegroups[0]:
                continue

            entry = BanEntry(param, setter, round(time()))

            # Check for existing ban
            for i, (string, _, _) in enumerate(list(ban_modes[mode])):
                if self.casefold(param) == self.casefold(string):
                    if adding:
                        # Update timestamp and setter
                        logger.debug("Replacing entry: %r -> %r",
                                     ban_modes[mode][i], entry)
                        ban_modes[mode][i] = entry
                    else:
                        # Delete ban
                        del ban_modes[mode][i]
                    return

            logger.debug("Adding entry: %r", entry)
            ban_modes[mode].append(entry)

        if send_request:
            logger.debug("Given status in %s", channel.name)
            self.send("MODE", [channel.name, modegroups[0]])

    @hook("commands", Numerics.RPL_BANLIST)
    @hook("commands", Numerics.RPL_EXCEPTLIST)
    @hook("commands", Numerics.RPL_INVITELIST)
    @hook("commands", Numerics.RPL_QUIETLIST)
    def list_numeric(self, event):
        params = event.line.params
        string = params[1]
        setter = Hostmask.parse(params[2])
        timestamp = int(params[3])

        entry = BanEntry(param, setter, timestamp)

        if event.line.command not in self.ban_numerics_modes:
            return

        # Mode letter lookup
        mode = self.ban_numerics_modes[event.line.command]

        channeltrack = self.get_extension("ChannelTrack")
        channel = channeltrack.get_channel(params[0])

        for i, (lstring, lsetter, ltimestamp) in enumerate(ban_modes[mode]):
            if lstring == string:
                # Check if known
                # We do this in case our clock is off and stuff is desynced,
                # because MODE added some entries.
                # FIXME - results in approx. O(n*m) behaviour of mode
                # listings!
                if timestamp != ltimestamp:
                    # Desyncs with this shouldn't happen!
                    assert (self.casefold(str(lsetter)) !=
                            self.casefold(str(setter)))

                    # Replace entry.
                    logger.debug("Replacing entry: %r -> %r",
                                 ban_modes[mode][i], entry)
                    ban_modes[mode][i] = entry

                return

        logger.debug("Adding entry: %r", entry)
        channel.ban_modes[mode].append(entry)
