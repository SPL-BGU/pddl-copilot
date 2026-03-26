;; 2 counters: make c0 > c1
(define (problem counters-p01)
  (:domain counters)
  (:objects c0 c1 - counter)
  (:init
    (= (value c0) 0)
    (= (value c1) 2)
    (= (max_int) 5))
  (:goal (> (value c0) (value c1))))
