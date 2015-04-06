#!/usr/bin/env python3
# Copyright © 2015 Andrew Wilcox and Elizabeth Myers.
# All rights reserved.
# This file is part of the PyIRC3 project. See LICENSE in the root directory
# for licensing information.


from collections.abc import Mapping
from functools import partial

from PyIRC.base import BaseExtension
from PyIRC.event import EventState
from PyIRC.numerics import Numerics


class AutoJoin(BaseExtension):

    """ This extension will autojoin the channels you specify, without flooding
    off the network.  The initial delay to first join and delay between each
    successive channel is customisable. """

    def __init__(self, base, **kwargs):
        """ Initialise the AutoJoin extension.

        join
          A Mapping (dictionary type) or Iterable of channels to join.
          If a Mapping is passed, keys are treated as channel names and values
          are used as keys to join the channel.
          If an Iterable is passed, each value is a channel and no keys are
          specified when joining.
        autojoin_wait_start
          How much time, in seconds, to wait for autojoin to begin.
          The default is 0.75 seconds.
        autojoin_wait_interval
          How much time, in seconds, to wait between each join.
          The default is 0.25 seconds.
        """

        self.base = base

        self.commands = {
            Numerics.RPL_WELCOME : self.autojoin,
        }

        self.hooks = {
            "disconnected" : self.close,
        }

        self.join_dict = kwargs['join']

        # If a list is passed in for join_dict, we will use a comprehension
        # to set null keys
        if not isinstance(self.join_dict, Mapping):
            self.join_dict = {channel : None for channel in self.join_dict}

        # Should be sufficient for end of MOTD
        self.wait_start = kwargs.get('autojoin_wait_start', 0.75)

        # Default is 4 per second
        self.wait_interval = kwargs.get('autojoin_wait_interval', 0.25)

        # Used for unexpected disconnect
        self.sched = []

    def do_join(self, params):
        self.send("JOIN", params)
        self.sched.pop(0)

    def autojoin(self, event):
        # Should be sufficient for end of MOTD and such
        t = self.wait_start

        for channel, key in self.join_dict.items():
            if key is None:
                params = [channel]
            else:
                params = [channel, key]

            sched = self.schedule(t, partial(self.do_join, params))
            self.sched.append(sched)

            t += self.wait_interval

    def close(self):
        for sched in self.sched:
            try:
                self.unschedule(sched)
            except ValueError:
                pass

        self.sched.clear()
