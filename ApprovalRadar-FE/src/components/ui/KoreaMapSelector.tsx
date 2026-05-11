import { useEffect, useRef, useState } from 'react';

interface KoreaMapSelectorProps {
  selectedLocation: string;
  onSelect: (location: string) => void;
}

export function KoreaMapSelector({ selectedLocation, onSelect }: KoreaMapSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgLoaded, setSvgLoaded] = useState(false);

  // 1. Fetch and inject SVG once
  useEffect(() => {
    fetch('/korea_map.svg')
      .then((res) => res.text())
      .then((svgString) => {
        if (containerRef.current) {
          containerRef.current.innerHTML = svgString;
          const svg = containerRef.current.querySelector('svg');
          if (svg) {
            svg.style.width = '100%';
            svg.style.height = 'auto';
            svg.style.maxHeight = '600px';
            svg.setAttribute('viewBox', '0 0 800 760'); // Keep original viewBox
            
            // Initial styling for all regions
            const regions = svg.querySelectorAll('path[id], g[id]');
            regions.forEach((region) => {
              if (region.id === '전국_시도_경계') {
                (region as HTMLElement).style.pointerEvents = 'none';
                return;
              }
              
              const el = region as HTMLElement;
              el.style.cursor = 'pointer';
              el.style.transition = 'all 0.2s ease-in-out';
              el.style.stroke = '#ffffff';
              el.style.strokeWidth = '2px';
              
              // Add title for tooltip if not exists
              if (!el.querySelector('title')) {
                const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
                title.textContent = region.id;
                region.appendChild(title);
              }
            });
            setSvgLoaded(true);
          }
        }
      })
      .catch(err => {
        console.error("Failed to load map svg", err);
      });
  }, []);

  // 2. Handle interactions and updates when selectedLocation or svgLoaded changes
  useEffect(() => {
    if (!svgLoaded || !containerRef.current) return;
    
    const svg = containerRef.current.querySelector('svg');
    if (!svg) return;

    const regions = svg.querySelectorAll('path[id], g[id]');
    
    const handleMouseEnter = (e: Event) => {
      const el = e.currentTarget as HTMLElement;
      if (el.id !== selectedLocation) {
        el.style.fill = '#cbd5e1'; // Tailwind slate-300
      }
    };

    const handleMouseLeave = (e: Event) => {
      const el = e.currentTarget as HTMLElement;
      if (el.id !== selectedLocation) {
        el.style.fill = '#f1f5f9'; // Tailwind slate-100
      } else {
        el.style.fill = '#2563eb'; // Brand color
      }
    };

    const handleClick = (e: Event) => {
      const el = e.currentTarget as HTMLElement;
      onSelect(el.id === selectedLocation ? '전체' : el.id); // Toggle off if clicked again
    };

    regions.forEach((region) => {
      if (region.id === '전국_시도_경계') return;
      
      const el = region as HTMLElement;
      
      // Set current color based on selectedLocation
      if (el.id === selectedLocation) {
        el.style.fill = '#2563eb'; // Brand color
      } else {
        el.style.fill = '#f1f5f9'; // Default color
      }

      // Attach events
      el.addEventListener('mouseenter', handleMouseEnter);
      el.addEventListener('mouseleave', handleMouseLeave);
      el.addEventListener('click', handleClick);
    });

    // Cleanup events on re-render
    return () => {
      regions.forEach((region) => {
        if (region.id === '전국_시도_경계') return;
        const el = region as HTMLElement;
        el.removeEventListener('mouseenter', handleMouseEnter);
        el.removeEventListener('mouseleave', handleMouseLeave);
        el.removeEventListener('click', handleClick);
      });
    };
  }, [selectedLocation, svgLoaded, onSelect]);

  return (
    <div className="w-full relative flex justify-center items-center p-4">
      {!svgLoaded && (
        <div className="absolute inset-0 flex justify-center items-center">
          <span className="text-text-muted text-sm animate-pulse">지도를 불러오는 중...</span>
        </div>
      )}
      <div ref={containerRef} className="w-full max-w-[500px]" />
    </div>
  );
}
