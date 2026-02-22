"""Math for movement regarding cardinal directions."""
from __future__ import annotations
from enum import Flag
from functools import reduce
import math


class Direction(Flag):
    """Cardinal directions for movement and rotation."""
    NONE = 0
    UP = 1 << 0
    RIGHT = 1 << 1
    DOWN = 1 << 2
    LEFT = 1 << 3
    ALL = UP | DOWN | LEFT | RIGHT

    def rotate(self, times: int, ccw: bool = False) -> Direction:
        """Rotate a direction by any number of right angles."""
        if len(self.components) > 1:
            rotated_components = [direction.rotate(times, ccw)
                                  for direction in self.components]
            return reduce(lambda a, b: a | b, rotated_components)
        assert self.value in {1, 2, 4, 8}
        value = int(math.log2(self.value))
        delta = -times if ccw else times
        return Direction(1 << ((value + delta) % 4))

    def difference(self, other: Direction) -> int:
        """Count 90-degree clockwise rotations from one direction to another."""
        if len(self.components) > 1:
            raise RuntimeError("cannot find difference with compound directions")
        assert self.value in {1, 2, 4, 8} and other.value in {1, 2, 4, 8}
        self_value, other_value = int(math.log2(self.value)), int(math.log2(other.value))
        return (self_value - other_value) % 4

    def get_subrect_indices(self) -> list[int]:
        """Get indices of a 3x3 grid that correspond to cardinal directions."""
        indices = []
        if self & Direction.UP:
            indices.append(1)
        if self & Direction.DOWN:
            indices.append(7)
        if self & Direction.LEFT:
            indices.append(3)
        if self & Direction.RIGHT:
            indices.append(5)
        return indices

    @property
    def components(self) -> list[Direction]:
        """A list of individual directions that compose a compound direction."""
        directions = []
        if self & Direction.UP:
            directions.append(Direction.UP)
        if self & Direction.DOWN:
            directions.append(Direction.DOWN)
        if self & Direction.LEFT:
            directions.append(Direction.LEFT)
        if self & Direction.RIGHT:
            directions.append(Direction.RIGHT)
        return directions


class MovementCombo(Flag):
    """Combination of directions to move in."""
    NONE = 0
    FORWARD = 1 << 0
    BACKWARD = 1 << 1
    LEFT = 1 << 2
    RIGHT = 1 << 3
    FORWARD_LEFT = FORWARD | LEFT
    FORWARD_RIGHT = FORWARD | RIGHT
    BACKWARD_LEFT = BACKWARD | LEFT
    BACKWARD_RIGHT = BACKWARD | RIGHT

    def resolved(self):
        """Resolve conflicting directions."""
        new = self
        if not self.is_legal:
            if self & MovementCombo.LEFT and self & MovementCombo.RIGHT:
                new = new & ~(MovementCombo.LEFT | MovementCombo.RIGHT)
            if self & MovementCombo.FORWARD and self & MovementCombo.BACKWARD:
                new = new & ~(MovementCombo.FORWARD | MovementCombo.BACKWARD)
        return new

    @property
    def is_legal(self):
        """Whether or not a combination of directions is legal."""
        return self.value in {0, 1, 2, 4, 5, 6, 8, 9, 10}
