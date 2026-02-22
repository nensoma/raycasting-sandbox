"""Cell management and logic."""
# pylint: disable=no-member
from __future__ import annotations

import pygame

from blocks import Wall, Mirror, Portal
from directions import Direction


TRANSPARENT = (0, 0, 0, 0)

def split_position(position: pygame.Vector2,
                   square_size: int) -> tuple[pygame.Vector2, pygame.Vector2]:
    """Split an absolute position into the cell it's in and its position in that cell."""
    cell_x, cell_pos_x = divmod(position.x, square_size)
    cell_y, cell_pos_y = divmod(position.y, square_size)
    return (pygame.Vector2(cell_x, cell_y),
            pygame.Vector2(cell_pos_x / square_size, cell_pos_y / square_size))

def get_closest_side(position: pygame.Vector2) -> Direction:
    """Find the closest side of a cell given a position inside the cell."""
    values = ((position.y, Direction.UP), (1-position.y, Direction.DOWN),
              (position.x, Direction.LEFT), (1-position.x, Direction.RIGHT))
    return min(values, key=lambda value: value[0])[1]

def get_enter_side(position: pygame.Vector2,
                   direction: pygame.Vector2) -> Direction:
    """Find which side of a cell a ray entered from."""
    from_position = get_closest_side(position)
    angle = pygame.Vector2(1, 0).angle_to(direction) % 360
    # double angle check handles edge cases where rays hit the wrong side
    match from_position:
        case Direction.UP:
            if angle <= 180:
                return from_position
            return Direction.RIGHT if 180 < angle <= 270 else Direction.LEFT
        case Direction.RIGHT:
            if 90 <= angle <= 270:
                return from_position
            return Direction.UP if angle < 90 else Direction.DOWN
        case Direction.DOWN:
            if angle >= 180:
                return from_position
            return Direction.RIGHT if 90 <= angle < 180 else Direction.LEFT
        case Direction.LEFT:
            if angle <= 90 or angle >= 270:
                return from_position
            return Direction.UP if 90 < angle <= 180 else Direction.DOWN
    return Direction.NONE


class Cell:
    """Individual map cell's type and rendering."""
    MAIN_COLOR = (255, 255, 255)
    MIRROR_COLOR = (64, 64, 64)
    PORTAL_COLOR = (128, 0, 255)

    def __init__(self, type_: Wall | Mirror | Portal | bool = False):
        self.type_ = type_

    def draw(self, location: tuple[int, int], cell_map: CellMap):
        """Draw a cell on a map."""
        index = location[1]*cell_map.columns + location[0]
        cell_rect = cell_map.get_cell_rect(*location, cell_map.square_size)
        match self.type_:
            case Wall.NORMAL:
                pygame.draw.rect(cell_map.surf, self.MAIN_COLOR, cell_rect)
            case Mirror():
                pygame.draw.rect(cell_map.surf, TRANSPARENT, cell_rect)
                pygame.draw.rect(cell_map.surf, self.MAIN_COLOR, cell_rect,
                                 width=int(cell_map.square_size/8))
                indices = self.type_.sides.get_subrect_indices()
                for index in indices:
                    mirror_rect = cell_map.get_cell_subrect(
                        *location, cell_map.square_size, index)
                    pygame.draw.rect(cell_map.surf, self.MIRROR_COLOR, mirror_rect)
            case Portal():
                pygame.draw.rect(cell_map.surf, self.MAIN_COLOR, cell_rect)
                pygame.draw.rect(cell_map.surf, TRANSPARENT, cell_rect,
                                 width=int(cell_map.square_size/8))
                indices = self.type_.get_subrect_indices()
                for index in indices:
                    portal_rect = cell_map.get_cell_subrect(
                        *location, cell_map.square_size, index)
                    pygame.draw.rect(cell_map.surf, self.PORTAL_COLOR, portal_rect)
            case False:
                pygame.draw.rect(cell_map.surf, TRANSPARENT, cell_rect)


class CellMap(pygame.sprite.Sprite):
    """Two-dimensional cell mapping of a map's layout in squares."""

    def __init__(self, size: tuple[int, int], square_size: int):
        super().__init__()
        self.size, self.square_size = size, square_size
        self.surf = pygame.Surface(size, pygame.SRCALPHA)
        self.rect: pygame.Rect = self.surf.get_rect()
        self.columns = size[0] // square_size
        self.rows = size[1] // square_size
        self.cells: list[Cell] = []
        self.cells.extend(Cell() for _ in range(self.columns*self.rows))

    def get_cell(self, x: int, y: int) -> Cell:
        """Get the value of a cell."""
        return self.cells[y*self.columns + x]

    def set_cell_type(self, x: int, y: int, new_type: Wall | Mirror | Portal | bool):
        """Set the value of a cell and update it on the map."""
        cell = self.get_cell(x, y)
        if (not isinstance(new_type, Portal) and isinstance(cell.type_, Portal)):
            for direction, linked in cell.type_.links.items():
                if linked is None:
                    continue
                self.unlink_sides((x, y), direction, *linked)
        cell.type_ = new_type
        cell.draw((x, y), self)

    def clear(self):
        """Clear all cells from the map."""
        for column in range(self.columns):
            for row in range(self.rows):
                self.set_cell_type(column, row, False)

    def link_sides(self, first_location: tuple[int, int], first_side: Direction,
                   second_location: tuple[int, int], second_side: Direction):
        """Link two unique cell sides together for portal mechanics."""
        if first_location == second_location:
            cell = self.get_cell(*first_location)
            new_type = (cell.type_ if isinstance(cell.type_, Portal)
                        else Portal())
            new_type.links[first_side] = (first_location, second_side)
            new_type.links[second_side] = (first_location, first_side)
            self.set_cell_type(*first_location, new_type)
        else:
            first_cell = self.get_cell(*first_location)
            second_cell = self.get_cell(*second_location)
            new_first_type = (first_cell.type_ if isinstance(first_cell.type_, Portal)
                              else Portal())
            new_second_type = (second_cell.type_ if isinstance(second_cell.type_, Portal)
                               else Portal())
            new_first_type.links[first_side] = (second_location, second_side)
            new_second_type.links[second_side] = (first_location, first_side)
            self.set_cell_type(*first_location, new_first_type)
            self.set_cell_type(*second_location, new_second_type)

    def unlink_sides(self, first_location: tuple[int, int], first_side: Direction,
                     second_location: tuple[int, int], second_side: Direction):
        """Unlink two unique cell sides linked together for portal mechanics."""
        if first_location == second_location:
            cell = self.get_cell(*first_location)
            if not isinstance(cell.type_, Portal):
                return
            cell.type_.links[first_side] = None
            cell.type_.links[second_side] = None
            if all(link is None for link in cell.type_.links.values()):
                cell.type_ = False
            cell.draw(first_location, self)
        else:
            first_cell = self.get_cell(*first_location)
            second_cell = self.get_cell(*second_location)
            if not (isinstance(first_cell.type_, Portal)
                    and isinstance(second_cell.type_, Portal)):
                return
            first_cell.type_.links[first_side] = None
            second_cell.type_.links[second_side] = None
            if all(link is None for link in first_cell.type_.links.values()):
                first_cell.type_ = False
            if all(link is None for link in second_cell.type_.links.values()):
                second_cell.type_ = False
            first_cell.draw(first_location, self)
            second_cell.draw(second_location, self)

    def portal_transform(self, location: pygame.Vector2,
                         direction: pygame.Vector2) -> tuple[pygame.Vector2, pygame.Vector2]:
        """Teleport from one portal to another, accounting for rotation."""
        cell, cell_pos = split_position(location, self.square_size)
        enter_side = get_closest_side(cell_pos)

        start_cell = self.get_cell(int(cell.x), int(cell.y))
        assert isinstance(start_cell.type_, Portal)
        if (linked := start_cell.type_.links[enter_side]) is None:
            return (location, direction)

        # base teleport from same face
        if enter_side in {Direction.UP, Direction.DOWN}:
            cell_pos.x = 1 - cell_pos.x
        if enter_side in {Direction.LEFT, Direction.RIGHT}:
            cell_pos.y = 1 - cell_pos.y
        direction.rotate_ip(180)

        # calculate rotation within cell
        other_location, other_side = linked
        rotations = other_side.difference(enter_side)
        direction.rotate_ip(90*rotations)
        cell_pos = {0: (cell_pos.x, cell_pos.y),
                    1: (1-cell_pos.y, cell_pos.x),
                    2: (1-cell_pos.x, 1-cell_pos.y),
                    3: (cell_pos.y, 1-cell_pos.x)}[rotations]

        # calculate new position after teleport
        location.x = (other_location[0] + cell_pos[0]) * self.square_size
        location.y = (other_location[1] + cell_pos[1]) * self.square_size

        return (location, direction)

    def in_bounds(self, position: pygame.Vector2) -> bool:
        """Check whether a position is within the bound of the map."""
        return 0 < position.x < self.size[0] and 0 < position.y < self.size[1]

    @staticmethod
    def get_cell_rect(x: int, y: int, square_size: int) -> tuple[int, int, int, int]:
        """Find the corresponsding rect of a cell on the map's surface."""
        return (x*square_size, y*square_size, square_size, square_size)

    @staticmethod
    def get_cell_subrect(x: int, y: int, square_size: int,
                         index: int) -> tuple[int, int, int, int]:
        """Get the subrect (3x3) of a map's cell by index."""
        if index not in range(9):
            raise RuntimeError("Subrect index must be an integer 0-9")
        top_left_x, top_left_y = x*square_size, y*square_size
        y_offset, x_offset = divmod(index, 3)
        return (round(top_left_x + (square_size/3)*x_offset),
                round(top_left_y + (square_size/3)*y_offset),
                round(square_size/3), round(square_size/3))
