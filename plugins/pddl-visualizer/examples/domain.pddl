(define (domain logistics)
  (:requirements :typing)
  (:types truck package location - object)
  (:predicates
    (at ?x - object ?l - location)
    (in ?p - package ?t - truck)
    (road ?l1 - location ?l2 - location))
  (:action drive
    :parameters (?t - truck ?from - location ?to - location)
    :precondition (and (at ?t ?from) (road ?from ?to))
    :effect (and (not (at ?t ?from)) (at ?t ?to)))
  (:action load
    :parameters (?p - package ?t - truck ?l - location)
    :precondition (and (at ?p ?l) (at ?t ?l))
    :effect (and (not (at ?p ?l)) (in ?p ?t)))
  (:action unload
    :parameters (?p - package ?t - truck ?l - location)
    :precondition (and (in ?p ?t) (at ?t ?l))
    :effect (and (not (in ?p ?t)) (at ?p ?l))))
