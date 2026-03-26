;; 3 counters: order them c0 < c1 < c2
(define (problem counters-p02)
  (:domain counters)
  (:objects c0 c1 c2 - counter)
  (:init
    (= (value c0) 3)
    (= (value c1) 1)
    (= (value c2) 2)
    (= (max_int) 5))
  (:goal (and (< (value c0) (value c1)) (< (value c1) (value c2)))))
