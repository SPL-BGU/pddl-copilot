;; 2 counters: both reach specific values
(define (problem counters-p03)
  (:domain counters)
  (:objects c0 c1 - counter)
  (:init
    (= (value c0) 1)
    (= (value c1) 4)
    (= (max_int) 5))
  (:goal (and (= (value c0) 3) (= (value c1) 1))))
