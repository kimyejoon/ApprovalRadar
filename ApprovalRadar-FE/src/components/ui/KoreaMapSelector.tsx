import { useEffect, useRef, useState } from 'react';

interface KoreaMapSelectorProps {
  selectedLocations: string[];
  onSelect: (locations: string[]) => void;
}

export function KoreaMapSelector({ selectedLocations, onSelect }: KoreaMapSelectorProps) {
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

  // 2. Handle interactions and updates when selectedLocations or svgLoaded changes
  useEffect(() => {
    if (!svgLoaded || !containerRef.current) return;
    
    const svg = containerRef.current.querySelector('svg');
    if (!svg) return;

    const regions = svg.querySelectorAll('path[id], g[id]');
    
    const isSelected = (id: string) => selectedLocations.includes(id);

    const applyStyle = (el: HTMLElement, hovered: boolean) => {
      if (isSelected(el.id)) {
        // Supabase accent style (Green outline with faint fill)
        el.style.fill = hovered ? 'rgba(62, 207, 142, 0.2)' : 'rgba(62, 207, 142, 0.1)';
        el.style.stroke = '#3ecf8e'; // Brand color
      } else {
        // Default style
        el.style.fill = hovered ? '#cbd5e1' : '#f1f5f9';
        el.style.stroke = '#ffffff';
      }
    };

    const handleMouseEnter = (e: Event) => {
      applyStyle(e.currentTarget as HTMLElement, true);
    };

    const handleMouseLeave = (e: Event) => {
      applyStyle(e.currentTarget as HTMLElement, false);
    };

    const handleClick = (e: Event) => {
      const el = e.currentTarget as HTMLElement;
      if (isSelected(el.id)) {
        onSelect(selectedLocations.filter(loc => loc !== el.id));
      } else {
        onSelect([...selectedLocations, el.id]);
      }
    };

    regions.forEach((region) => {
      if (region.id === '전국_시도_경계') return;
      
      const el = region as HTMLElement;
      
      applyStyle(el, false);

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
  }, [selectedLocations, svgLoaded, onSelect]);

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
