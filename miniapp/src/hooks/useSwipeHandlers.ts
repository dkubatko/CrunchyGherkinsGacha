import { useSwipeable } from 'react-swipeable';

interface UseSwipeHandlersProps {
  cardsLength: number;
  currentIndex: number;
  onIndexChange: (newIndex: number) => void;
  onTiltReset: () => void;
}

export const useSwipeHandlers = ({ 
  cardsLength, 
  currentIndex, 
  onIndexChange, 
  onTiltReset 
}: UseSwipeHandlersProps) => {
  return useSwipeable({
    onSwipedLeft: () => {
      const newIndex = (currentIndex + 1) % cardsLength;
      onIndexChange(newIndex);
      onTiltReset();
    },
    onSwipedRight: () => {
      const newIndex = currentIndex === 0 ? cardsLength - 1 : currentIndex - 1;
      onIndexChange(newIndex);
      onTiltReset();
    },
    preventScrollOnSwipe: true,
    trackMouse: true
  });
};