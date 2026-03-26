(define (problem depots-p01)
  (:domain depots)
  (:objects
    depot0 - depot
    distributor0 - distributor
    truck0 - truck
    hoist0 hoist1 - hoist
    pallet0 pallet1 - pallet
    crate0 - crate)
  (:init
    (at truck0 depot0)
    (at hoist0 depot0)
    (available hoist0)
    (at hoist1 distributor0)
    (available hoist1)
    (at pallet0 depot0)
    (clear pallet0)
    (at pallet1 distributor0)
    (at crate0 distributor0)
    (on crate0 pallet1)
    (clear crate0))
  (:goal (and (on crate0 pallet0))))
