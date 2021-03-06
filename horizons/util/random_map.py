# ###################################################
# Copyright (C) 2011 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
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
import random
import tempfile
import sys
import shutil
import re
import string
import time

from horizons.util import Circle, Rect, Point, DbReader
from horizons.constants import GROUND, PATHS
from horizons.ext.enum import Enum

# this is how a random island id looks like (used for creation)
_random_island_id_template = "random:${creation_method}:${width}:${height}:${seed}"

# you can check for a random island id with this:
_random_island_id_regexp = r"random:([0-9]+):([0-9]+):([0-9]+):([\-]?[0-9]+)"


def is_random_island_id_string(id_string):
	"""Returns whether id_string is an instance of a random island id string"""
	return bool(re.match(_random_island_id_regexp, id_string))

def create_random_island(id_string):
	"""Creates a random island as sqlite db.
	It is rather primitive; it places shapes on the dict.
	@param id_string: random island id string
	@return: sqlite db reader containing island
	"""
	# NOTE: the tilesystem will be redone soon, so constants indicating grounds are temporary
	# here and will have to be changed anyways.
	match_obj = re.match(_random_island_id_regexp, id_string)
	assert match_obj
	creation_method, width, height, seed = [ long(i) for i in match_obj.groups() ]

	rand = random.Random(seed)

	map_dict = {}

	# creation_method 0 - standard small island for the 3x3 grid
	# creation_method 1 - large island

	# place this number of shapes
	for i in xrange( int(float(width+height)/2 * 1.5) ):
		x = rand.randint(8, width - 8)
		y = rand.randint(8, height - 8)

		# place shape determined by shape_id on (x, y)
		if creation_method == 0:
			shape_id = rand.randint(3, 5)
		elif creation_method == 1:
			shape_id = rand.randint(5, 8)

		if rand.randint(1,4) == 1:
			# use a rect
			if creation_method == 0:
				for shape_coord in Rect.init_from_topleft_and_size(x-3, y-3, 5, 5).tuple_iter():
					map_dict[shape_coord] = True
			elif creation_method == 1:
				for shape_coord in Rect.init_from_topleft_and_size(x-5, y-5, 8, 8).tuple_iter():
					map_dict[shape_coord] = True

		else:
			# use a circle, where radius is determined by shape_id
			for shape_coord in Circle(Point(x, y), shape_id).tuple_iter():
				map_dict[shape_coord] = True

	# write values to db
	map_db = DbReader(":memory:")
	map_db("CREATE TABLE ground(x INTEGER NOT NULL, y INTEGER NOT NULL, ground_id INTEGER NOT NULL)")
	map_db("CREATE TABLE island_properties(name TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)")
	map_db("BEGIN TRANSACTION")

	# add grass tiles
	for x, y in map_dict.iterkeys():
		map_db("INSERT INTO ground VALUES(?, ?, ?)", x, y, GROUND.DEFAULT_LAND)

	def fill_tiny_spaces(tile):
		"""Fills 1 tile gulfs and straits with the specified tile
		@param tile: ground tile to fill with
		"""

		neighbours = [(-1, 0), (0, -1), (0, 1), (1, 0)]
		corners = [(-1, -1), (-1, 1)]
		knight_moves = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
		bad_configs = set([0, 1 << 0, 1 << 1, 1 << 2, 1 << 3, (1 << 0) | (1 << 3), (1 << 1) | (1 << 2)])

		while True:
			to_fill = {}
			for x, y in map_dict.iterkeys():
				for x_offset, y_offset in neighbours:
					x2 = x + x_offset
					y2 = y + y_offset
					if (x2, y2) in map_dict:
						continue
					# (x2, y2) is now a point just off the island

					neighbours_dirs = 0
					for i in range(len(neighbours)):
						x3 = x2 + neighbours[i][0]
						y3 = y2 + neighbours[i][1]
						if (x3, y3) not in map_dict:
							neighbours_dirs |= (1 << i)
					if neighbours_dirs in bad_configs:
						# part of a straight 1 tile gulf
						to_fill[(x2, y2)] = True
					else:
						for x_offset, y_offset in corners:
							x3 = x2 + x_offset
							y3 = y2 + y_offset
							x4 = x2 - x_offset
							y4 = y2 - y_offset
							if (x3, y3) in map_dict and (x4, y4) in map_dict:
								# part of a diagonal 1 tile gulf
								to_fill[(x2, y2)] = True
								break

				# block 1 tile straits
				for x_offset, y_offset in knight_moves:
					x2 = x + x_offset
					y2 = y + y_offset
					if (x2, y2) not in map_dict:
						continue
					if abs(x_offset) == 1:
						y2 = y + y_offset / 2
						if (x2, y2) in map_dict or (x, y2) in map_dict:
							continue
					else:
						x2 = x + x_offset / 2
						if (x2, y2) in map_dict or (x2, y) in map_dict:
							continue
					to_fill[(x2, y2)] = True

			if to_fill:
				for x, y in to_fill.iterkeys():
					map_dict[(x, y)] = tile
					map_db("INSERT INTO ground VALUES(?, ?, ?)", x, y, tile)
			else:
				break

	# possible movement directions
	all_moves = {
		'sw' : (-1, -1),
		'w'  : (-1, 0),
		'nw' : (-1, 1),
		's'  : (0, -1),
		'n'  : (0, 1),
		'se' : (1, -1),
		'e'  : (1, 0),
		'ne' : (1, 1)
		}

	def get_island_outline():
		"""
		@return: the points just off the island as a dict
		"""
		result = {}
		for x, y in map_dict.iterkeys():
			for offset_x, offset_y in all_moves.itervalues():
				coords = (x + offset_x, y + offset_y)
				if coords not in map_dict:
					result[coords] = True
		return result

	# add grass to sand tiles
	fill_tiny_spaces(GROUND.DEFAULT_LAND)
	outline = get_island_outline()
	for x, y in outline.iterkeys():
		filled = []
		for dir in sorted(all_moves):
			coords = (x + all_moves[dir][1], y + all_moves[dir][0])
			if coords in map_dict:
				filled.append(dir)

		tile = None
		# straight coast or 1 tile U-shaped gulfs
		if filled == ['s', 'se', 'sw'] or filled == ['s']:
			tile = GROUND.SAND_NORTH
		elif filled == ['e', 'ne', 'se'] or filled == ['e']:
			tile = GROUND.SAND_WEST
		elif filled == ['n', 'ne', 'nw'] or filled == ['n']:
			tile = GROUND.SAND_SOUTH
		elif filled == ['nw', 'sw', 'w'] or filled == ['w']:
			tile = GROUND.SAND_EAST
		# slight turn (looks best with straight coast)
		elif filled == ['e', 'se'] or filled == ['e', 'ne']:
			tile = GROUND.SAND_WEST
		elif filled == ['n', 'ne'] or filled == ['n', 'nw']:
			tile = GROUND.SAND_SOUTH
		elif filled == ['nw', 'w'] or filled == ['sw', 'w']:
			tile = GROUND.SAND_EAST
		elif filled == ['s', 'sw'] or filled == ['s', 'se']:
			tile = GROUND.SAND_NORTH
		# sandy corner
		elif filled == ['se']:
			tile = GROUND.SAND_NORTHWEST1
		elif filled == ['ne']:
			tile = GROUND.SAND_SOUTHWEST1
		elif filled == ['nw']:
			tile = GROUND.SAND_SOUTHEAST1
		elif filled == ['sw']:
			tile = GROUND.SAND_NORTHEAST1
		# grassy corner
		elif 3 <= len(filled) <= 5:
			coast_set = set(filled)
			if 'e' in coast_set and 'se' in coast_set and 's' in coast_set:
				tile = GROUND.SAND_NORTHEAST3
			elif 's' in coast_set and 'sw' in coast_set and 'w' in coast_set:
				tile = GROUND.SAND_NORTHWEST3
			elif 'w' in coast_set and 'nw' in coast_set and 'n' in coast_set:
				tile = GROUND.SAND_SOUTHWEST3
			elif 'n' in coast_set and 'ne' in coast_set and 'e' in coast_set:
				tile = GROUND.SAND_SOUTHEAST3

		assert tile
		map_db("INSERT INTO ground VALUES(?, ?, ?)", x, y, tile)

	for coords, type in outline.iteritems():
		map_dict[coords] = type

	# add sand to shallow water tiles
	fill_tiny_spaces(GROUND.SAND)
	outline = get_island_outline()
	for x, y in outline.iterkeys():
		filled = []
		for dir in sorted(all_moves):
			coords = (x + all_moves[dir][1], y + all_moves[dir][0])
			if coords in map_dict:
				filled.append(dir)

		tile = None
		# straight coast or 1 tile U-shaped gulfs
		if filled == ['s', 'se', 'sw'] or filled == ['s']:
			tile = GROUND.COAST_NORTH
		elif filled == ['e', 'ne', 'se'] or filled == ['e']:
			tile = GROUND.COAST_WEST
		elif filled == ['n', 'ne', 'nw'] or filled == ['n']:
			tile = GROUND.COAST_SOUTH
		elif filled == ['nw', 'sw', 'w'] or filled == ['w']:
			tile = GROUND.COAST_EAST
		# slight turn (looks best with straight coast)
		elif filled == ['e', 'se'] or filled == ['e', 'ne']:
			tile = GROUND.COAST_WEST
		elif filled == ['n', 'ne'] or filled == ['n', 'nw']:
			tile = GROUND.COAST_SOUTH
		elif filled == ['nw', 'w'] or filled == ['sw', 'w']:
			tile = GROUND.COAST_EAST
		elif filled == ['s', 'sw'] or filled == ['s', 'se']:
			tile = GROUND.COAST_NORTH
		# mostly wet corner
		elif filled == ['se']:
			tile = GROUND.COAST_NORTHWEST1
		elif filled == ['ne']:
			tile = GROUND.COAST_SOUTHWEST1
		elif filled == ['nw']:
			tile = GROUND.COAST_SOUTHEAST1
		elif filled == ['sw']:
			tile = GROUND.COAST_NORTHEAST1
		# mostly dry corner
		elif 3 <= len(filled) <= 5:
			coast_set = set(filled)
			if 'e' in coast_set and 'se' in coast_set and 's' in coast_set:
				tile = GROUND.COAST_NORTHEAST3
			elif 's' in coast_set and 'sw' in coast_set and 'w' in coast_set:
				tile = GROUND.COAST_NORTHWEST3
			elif 'w' in coast_set and 'nw' in coast_set and 'n' in coast_set:
				tile = GROUND.COAST_SOUTHWEST3
			elif 'n' in coast_set and 'ne' in coast_set and 'e' in coast_set:
				tile = GROUND.COAST_SOUTHEAST3

		assert tile
		map_db("INSERT INTO ground VALUES(?, ?, ?)", x, y, tile)

	for coords, type in outline.iteritems():
		map_dict[coords] = type

	# add shallow water to deep water tiles
	fill_tiny_spaces(GROUND.SHALLOW_WATER)
	outline = get_island_outline()
	for x, y in outline.iterkeys():
		filled = []
		for dir in sorted(all_moves):
			coords = (x + all_moves[dir][1], y + all_moves[dir][0])
			if coords in map_dict:
				filled.append(dir)

		tile = None
		# straight coast or 1 tile U-shaped gulfs
		if filled == ['s', 'se', 'sw'] or filled == ['s']:
			tile = GROUND.DEEP_WATER_NORTH
		elif filled == ['e', 'ne', 'se'] or filled == ['e']:
			tile = GROUND.DEEP_WATER_WEST
		elif filled == ['n', 'ne', 'nw'] or filled == ['n']:
			tile = GROUND.DEEP_WATER_SOUTH
		elif filled == ['nw', 'sw', 'w'] or filled == ['w']:
			tile = GROUND.DEEP_WATER_EAST
		# slight turn (looks best with straight coast)
		elif filled == ['e', 'se'] or filled == ['e', 'ne']:
			tile = GROUND.DEEP_WATER_WEST
		elif filled == ['n', 'ne'] or filled == ['n', 'nw']:
			tile = GROUND.DEEP_WATER_SOUTH
		elif filled == ['nw', 'w'] or filled == ['sw', 'w']:
			tile = GROUND.DEEP_WATER_EAST
		elif filled == ['s', 'sw'] or filled == ['s', 'se']:
			tile = GROUND.DEEP_WATER_NORTH
		# mostly deep corner
		elif filled == ['se']:
			tile = GROUND.DEEP_WATER_NORTHWEST1
		elif filled == ['ne']:
			tile = GROUND.DEEP_WATER_SOUTHWEST1
		elif filled == ['nw']:
			tile = GROUND.DEEP_WATER_SOUTHEAST1
		elif filled == ['sw']:
			tile = GROUND.DEEP_WATER_NORTHEAST1
		# mostly shallow corner
		elif 3 <= len(filled) <= 5:
			coast_set = set(filled)
			if 'e' in coast_set and 'se' in coast_set and 's' in coast_set:
				tile = GROUND.DEEP_WATER_NORTHEAST3
			elif 's' in coast_set and 'sw' in coast_set and 'w' in coast_set:
				tile = GROUND.DEEP_WATER_NORTHWEST3
			elif 'w' in coast_set and 'nw' in coast_set and 'n' in coast_set:
				tile = GROUND.DEEP_WATER_SOUTHWEST3
			elif 'n' in coast_set and 'ne' in coast_set and 'e' in coast_set:
				tile = GROUND.DEEP_WATER_SOUTHEAST3

		assert tile
		map_db("INSERT INTO ground VALUES(?, ?, ?)", x, y, tile)

	map_db("COMMIT")
	return map_db


def generate_map(seed = None) :
	"""Generates a whole map.
	@param seed: argument passed to random.seed
	@return filename to the sqlite db containing the new map"""
	rand = random.Random(seed)

	filename = tempfile.mkstemp()[1]
	shutil.copyfile(PATHS.SAVEGAME_TEMPLATE, filename)

	db = DbReader(filename)

	island_space = (35, 35)
	island_min_size = (25, 25)
	island_max_size = (28, 28)

	method = rand.randint(0, 1) # choose map creation method

	if method == 0:
		# generate up to 9 islands
		number_of_islands = 0
		for i in Rect.init_from_topleft_and_size(0, 0, 2, 2):
			if rand.randint(0, 2) != 0: # 2/3 chance for an island here
				number_of_islands = number_of_islands + 1
				x = int( i.x * island_space[0] * (rand.random()/6 + 0.90) )
				y = int( i.y * island_space[1] *  (rand.random()/6 + 0.90) )
				island_seed = rand.randint(-sys.maxint, sys.maxint)
				island_params = {'creation_method': 0, 'seed': island_seed, \
								 'width': rand.randint(island_min_size[0], island_max_size[0]), \
								 'height': rand.randint(island_min_size[1], island_max_size[1])}

				island_string = string.Template(_random_island_id_template).safe_substitute(island_params)

				db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)

		# if there is 1 or 0 islands created, it places 1 large island in the centre
		if number_of_islands == 0:
			x = 20
			y = 20
			island_seed = rand.randint(-sys.maxint, sys.maxint)
			island_params = {'creation_method': 1, 'seed': island_seed, \
							 'width': rand.randint(island_min_size[0] * 2, island_max_size[0] * 2), \
							 'height': rand.randint(island_min_size[1] * 2, island_max_size[1] * 2)}
			island_string = string.Template(_random_island_id_template).safe_substitute(island_params)

			db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)

		elif number_of_islands == 1:
			db("DELETE FROM island")

			x = 20
			y = 20
			island_seed = rand.randint(-sys.maxint, sys.maxint)
			island_params = {'creation_method': 1, 'seed': island_seed, \
							 'width': rand.randint(island_min_size[0] * 2, island_max_size[0] * 2), \
							 'height': rand.randint(island_min_size[1] * 2, island_max_size[1] * 2)}

			island_string = string.Template(_random_island_id_template).safe_substitute(island_params)

			db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)

	elif method == 1:
		# places 1 large island in the centre
		x = 20
		y = 20
		island_seed = rand.randint(-sys.maxint, sys.maxint)
		island_params = {'creation_method': 1, 'seed': island_seed, \
						 'width': rand.randint(island_min_size[0] * 2, island_max_size[0] * 2), \
						 'height': rand.randint(island_min_size[1] * 2, island_max_size[1] * 2)}
		island_string = string.Template(_random_island_id_template).safe_substitute(island_params)

		db("INSERT INTO island (x, y, file) VALUES(?, ?, ?)", x, y, island_string)

	return filename

