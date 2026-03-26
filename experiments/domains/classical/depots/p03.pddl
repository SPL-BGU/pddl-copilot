(define (problem depots-p03)
  (:domain depots)
  (:objects
    depot0 - depot
    distributor0 distributor1 - distributor
    truck0 - truck
    hoist0 hoist1 hoist2 - hoist
    pallet0 pallet1 pallet2 - pallet
    crate0 crate1 - crate)
  (:init
    (at truck0 depot0)
    (at hoist0 depot0)
    (available hoist0)
    (at hoist1 distributor0)
    (available hoist1)
    (at hoist2 distributor1)
    (available hoist2)
    (at pallet0 depot0)
    (at crate0 depot0)
    (on crate0 pallet0)
    (clear crate0)
    (at pallet1 distributor0)
    (clear pallet1)
    (at pallet2 distributor1)
    (at crate1 distributor1)
    (on crate1 pallet2)
    (clear crate1))
  (:goal (and (on crate0 pallet1) (on crate1 pallet0))))
