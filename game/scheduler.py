# ###################################################
# Copyright (C) 2008 The OpenAnnoTeam
# team@openanno.org
# This file is part of OpenAnno.
#
# OpenAnno is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

import game.main

class Scheduler():
	""""Class providing timed callbacks.
	To start a timed callback, call add_new_object() to make the TimingThread Class create a CallbackObject for you.
	"""
	def __init__(self):
		self.schedule = {}
		self.cur_tick = 0
		game.main.game.timer.add_call(self.tick)

	def tick(self, tick_id):
		"""Threads main loop
		@var tick_id: int id of the tick.
		"""
		self.cur_tick = tick_id
		if self.schedule.has_key(self.cur_tick):
			for object in self.schedule[self.cur_tick]:
				object.callback()
				if object.loops > 0 or object.loops is -1:
					self.add_object(object) # readd object
			del self.schedule[self.cur_tick]

	def add_object(self, object):
		"""Adds a new CallbackObject instance to the callbacks list
		@var object: CallbackObject type object, containing all neccessary  information
		"""
		if not self.schedule.has_key(self.cur_tick + object.runin):
			self.schedule[self.cur_tick + object.runin] = []
		if object.loops > 0:
			object.loops -= 1
		self.schedule[self.cur_tick + object.runin].append(object)

	def add_new_object(self, callback, parent_class, runin=1, loops=1):
		"""Creates a new CallbackObject instance and calls the self.add_object() function.
		@var callback: lambda function callback, which is called runin ticks.
		@var parent_class: class instance the function belongs to.
		@var runin: int number of ticks after which the callback is called. Standard is 1, run next tick.
		@var loops: How often the callback is called. -1 = infinit times. Standard is 1, run once."""
		object = CallbackObject(callback, parent_class, runin, loops)
		self.add_object(object)

	def rem_all_classinst_calls(self, class_inst):
		"""Removes all callbacks from the scheduler that belong to the class instance class_inst."""
		for key in self.schedule:
			for object in self.schedule[key]:
				if object.parent_class is class_inst:
					self.schedule[key].remove(object)

class CallbackObject():
	"""Class used by the TimerManager Class to organize callbacks."""
	def __init__(self,  callback, parent_class, runin=1, loops=1):
		"""Creates the CallbackObject instance.
		@var callback: lambda function callback, which is called runin ticks.
		@var parent_class: class instance the original function(not the lambda function!) belongs to.
		@var runin: int number of ticks after which the callback is called. Standard is 1, run next tick.
		@var loops: How often the callback is called. -1 = infinit times. Standard is 1, run once.
		"""
		self.runin = runin
		self.callback = callback
		self.loops = loops
		self.parent_class = parent_class
