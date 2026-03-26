;; 3 blocks: stack A on B on C
(define (problem bw-p01)
  (:domain blocksworld)
  (:objects a b c)
  (:init
    (ontable a) (ontable b) (ontable c)
    (clear a) (clear b) (clear c)
    (handempty))
  (:goal (and (on a b) (on b c))))
