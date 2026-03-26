(define (domain counters)
  (:requirements :typing :numeric-fluents)
  (:types counter)
  (:functions
    (value ?c - counter)
    (max_int))

  (:action increment
    :parameters (?c - counter)
    :precondition (< (value ?c) (max_int))
    :effect (increase (value ?c) 1))

  (:action decrement
    :parameters (?c - counter)
    :precondition (> (value ?c) 0)
    :effect (decrease (value ?c) 1)))
