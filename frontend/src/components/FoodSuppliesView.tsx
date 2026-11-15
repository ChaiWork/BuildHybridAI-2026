import React, { useState } from 'react';
import {
  Package,
  Utensils,
  Droplets,
  AlertTriangle,
  Clock,
  Plus,
  Trash2,
  Edit3,
  RefreshCw,
  Calculator,
  CheckCircle2,
  TrendingDown,
  ShieldAlert,
  Sliders,
  History,
  ArrowUpRight,
} from 'lucide-react';
import {
  FullSystemState,
  FoodItemRecord,
  FoodItemStatus,
  SupplyProjectionResult,
} from '../types';

interface Props {
  state: FullSystemState;
  apiBase: string;
  onStateUpdate: (newState: FullSystemState) => void;
  onNavigate?: (tab: string) => void;
}

const FOOD_CATEGORIES = [
  'Freeze-dried meals',
  'Ready-to-eat meals',
  'Snacks',
  'Fruits and vegetables',
  'Protein sources',
  'Beverages',
  'Emergency food supplies',
  'Potable Water & Hydration',
];

export const FoodSuppliesView: React.FC<Props> = ({
  state,
  apiBase,
  onStateUpdate,
  onNavigate,
}) => {
  const foodState = state.food_state;
  const [activeSubTab, setActiveSubTab] = useState<
    'dashboard' | 'consume_resupply' | 'projections' | 'nutrition' | 'history'
  >('dashboard');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [busy, setBusy] = useState<boolean>(false);
  const [bannerMsg, setBannerMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  // Add New Food Item Modal / Drawer state
  const [showAddForm, setShowAddForm] = useState<boolean>(false);
  const [newItem, setNewItem] = useState({
    name: '',
    category: 'Freeze-dried meals',
    quantity: 30,
    serving_size: '1 rehydratable pouch (230g)',
    unit: 'portions',
    calories_per_serving: 480,
    protein_g: 26,
    carbs_g: 58,
    fat_g: 14,
    water_ml_per_serving: 180,
    vitamin_d_iu: 240,
    calcium_mg: 200,
    nutrition_complete: true,
    storage_requirements: 'Ambient Dry Galley Rack (18–24°C)',
    bay_location: 'Galley G1 · Bay C',
    expiry_sol: (foodState?.mission_config.current_mission_sol || 184) + 360,
    min_threshold: 20,
    critical_threshold: 8,
    daily_ration_per_astronaut: 0.5,
    food_source: 'User-Entered Mission Inventory',
    notes: '',
  });

  // Inline quantity edit state
  const [editingUid, setEditingUid] = useState<string | null>(null);
  const [editQty, setEditQty] = useState<number>(0);
  const [editNotes, setEditNotes] = useState<string>('');

  // Meal Consumption Form
  const [consumeForm, setConsumeForm] = useState({
    food_item_uid: foodState?.items?.[0]?.item_uid || 'FOOD-FD-001',
    quantity_consumed: 1.0,
    meal_type: 'Dinner',
    extra_water_ml: 250,
    notes: '',
  });

  // Resupply / Harvest Form
  const [resupplyForm, setResupplyForm] = useState({
    food_item_uid: foodState?.items?.[0]?.item_uid || 'FOOD-FD-001',
    quantity_added: 24.0,
    event_type: 'RESUPPLY_DELIVERY',
    source: 'Pre-Positioned Cargo Module B Transfer',
    authorised_by: `${state.astronaut.name} (${state.astronaut.role})`,
    notes: '',
  });

  // Supply Projection Calculator (initialized with prompt's 120 portions / 2 astronauts / 3 portions/day = 20 days example)
  const [calcInput, setCalcInput] = useState({
    total_portions: 120,
    astronaut_count: 2,
    portions_per_astronaut_per_day: 3.0,
  });
  const [calcResult, setCalcResult] = useState<SupplyProjectionResult | null>(null);

  // Per-astronaut Nutrition Targets Form
  const curTargets = foodState?.nutrition_overview?.targets;
  const [targetForm, setTargetForm] = useState({
    calories_target_kcal: curTargets?.calories_target_kcal ?? 2850,
    protein_target_g: curTargets?.protein_target_g ?? 115,
    carbs_target_g: curTargets?.carbs_target_g ?? 360,
    fat_target_g: curTargets?.fat_target_g ?? 95,
    water_target_ml: curTargets?.water_target_ml ?? 2600,
    vitamin_d_target_iu: curTargets?.vitamin_d_target_iu ?? 800,
    calcium_target_mg: curTargets?.calcium_target_mg ?? 1200,
    notes: curTargets?.notes ?? '',
  });

  if (!foodState) {
    return (
      <div className="mc-card p-6 text-sm text-[#8E95A8]">
        Loading Food & Life-Support Supplies telemetry...
      </div>
    );
  }

  const {
    summary,
    mission_config,
    primary_meal_projection,
    category_projections,
    nutrition_overview,
    items,
    food_alerts,
    consumption_history,
    resupply_history,
  } = foodState;

  const statusBadge = (st: FoodItemStatus | string) => {
    switch (st) {
      case 'AVAILABLE':
        return (
          <span className="mc-pill bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            Available
          </span>
        );
      case 'RUNNING_LOW':
        return (
          <span className="mc-pill bg-amber-500/15 text-amber-300 border border-amber-500/30">
            Running Low
          </span>
        );
      case 'EXPIRING_SOON':
        return (
          <span className="mc-pill bg-amber-500/20 text-amber-200 border border-amber-400/40">
            Expiring Soon
          </span>
        );
      case 'CRITICAL':
        return (
          <span className="mc-pill bg-rose-500/20 text-rose-300 border border-rose-500/40">
            Critical
          </span>
        );
      case 'EXPIRED':
        return (
          <span className="mc-pill bg-rose-600/25 text-rose-200 border border-rose-500/50">
            Expired (Do Not Consume)
          </span>
        );
      default:
        return <span className="mc-pill bg-white/10 text-[#E5E5E4]">{st}</span>;
    }
  };

  const filteredItems = items.filter((item) => {
    if (categoryFilter !== 'ALL' && item.category !== categoryFilter) return false;
    if (statusFilter !== 'ALL' && item.status !== statusFilter) return false;
    return true;
  });

  const handleAddFoodItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newItem.name.trim()) return;
    setBusy(true);
    setBannerMsg(null);
    try {
      const res = await fetch(`${apiBase}/api/food/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...newItem,
          micronutrients: {
            vitamin_d_iu: Number(newItem.vitamin_d_iu) || 0,
            calcium_mg: Number(newItem.calcium_mg) || 0,
          },
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to add food item');
      if (data.state) onStateUpdate(data.state);
      setShowAddForm(false);
      setNewItem({ ...newItem, name: '', notes: '' });
      setBannerMsg({ type: 'ok', text: `Added "${data.item.name}" to galley inventory.` });
    } catch (err: any) {
      setBannerMsg({ type: 'err', text: err.message || 'Error adding food item' });
    } finally {
      setBusy(false);
    }
  };

  const handleSaveEditQuantity = async (item: FoodItemRecord) => {
    setBusy(true);
    setBannerMsg(null);
    try {
      const res = await fetch(`${apiBase}/api/food/items/${item.item_uid}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quantity: Number(editQty),
          notes: editNotes || item.notes,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update quantity');
      if (data.state) onStateUpdate(data.state);
      setEditingUid(null);
      setBannerMsg({
        type: 'ok',
        text: `Updated "${item.name}" stock to ${editQty} ${item.unit}.`,
      });
    } catch (err: any) {
      setBannerMsg({ type: 'err', text: err.message || 'Failed to update item' });
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveItem = async (item: FoodItemRecord) => {
    setBusy(true);
    setBannerMsg(null);
    try {
      const reason =
        item.status === 'EXPIRED'
          ? `Disposed expired ration (Sol ${item.expiry_sol})`
          : 'Removed unavailable ration during galley audit';
      const res = await fetch(
        `${apiBase}/api/food/items/${item.item_uid}?reason=${encodeURIComponent(reason)}`,
        { method: 'DELETE' }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to remove item');
      if (data.state) onStateUpdate(data.state);
      setBannerMsg({ type: 'ok', text: `Removed "${item.name}" from active inventory.` });
    } catch (err: any) {
      setBannerMsg({ type: 'err', text: err.message || 'Error removing item' });
    } finally {
      setBusy(false);
    }
  };

  const handleRecordConsumption = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBannerMsg(null);
    try {
      const res = await fetch(`${apiBase}/api/food/consume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(consumeForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Consumption logging blocked');
      if (data.state) onStateUpdate(data.state);
      setBannerMsg({
        type: 'ok',
        text: `Logged ${data.consumption.quantity_consumed} ${data.consumption.unit} of "${data.consumption.food_name}" (${consumeForm.meal_type}). Remaining stock: ${data.consumption.remaining_quantity} ${data.consumption.unit}.`,
      });
      setConsumeForm({ ...consumeForm, notes: '' });
    } catch (err: any) {
      setBannerMsg({ type: 'err', text: err.message || 'Failed to record meal' });
    } finally {
      setBusy(false);
    }
  };

  const handleRecordResupply = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBannerMsg(null);
    try {
      const res = await fetch(`${apiBase}/api/food/resupply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(resupplyForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to record resupply');
      if (data.state) onStateUpdate(data.state);
      setBannerMsg({
        type: 'ok',
        text: `Recorded +${data.resupply.quantity_added} ${data.resupply.unit} resupply for "${data.resupply.food_name}". New stock: ${data.resupply.quantity_after} ${data.resupply.unit}.`,
      });
      setResupplyForm({ ...resupplyForm, notes: '' });
    } catch (err: any) {
      setBannerMsg({ type: 'err', text: err.message || 'Failed to record resupply' });
    } finally {
      setBusy(false);
    }
  };

  const handleRunProjectionCalc = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await fetch(`${apiBase}/api/food/estimate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...calcInput,
          current_sol: mission_config.current_mission_sol,
          planned_mission_end_sol: mission_config.planned_mission_end_sol,
          next_resupply_sol: mission_config.next_resupply_sol,
        }),
      });
      const data = await res.json();
      setCalcResult(data);
    } finally {
      setBusy(false);
    }
  };

  const handleSaveNutritionTargets = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setBannerMsg(null);
    try {
      const res = await fetch(`${apiBase}/api/food/targets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          crew_id: state.active_crew_id,
          ...targetForm,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to save nutrition targets');
      if (data.state) onStateUpdate(data.state);
      setBannerMsg({
        type: 'ok',
        text: `Updated personal mission nutrition targets for ${state.astronaut.name}.`,
      });
    } catch (err: any) {
      setBannerMsg({ type: 'err', text: err.message || 'Failed to update targets' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Sub-Navigation */}
      <div className="mc-card p-6">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5 mb-2">
              <h1 className="text-2xl font-bold text-[#FAF9FA] tracking-tight">
                Food &amp; Life-Support Supplies
              </h1>
              <span className="mc-pill bg-[#A5D8FF]/15 text-[#A5D8FF] border border-[#A5D8FF]/30">
                Sol {mission_config.current_mission_sol} Galley &amp; ECLSS Reserve
              </span>
              <span className="mc-pill bg-white/5 text-[#8E95A8] border border-white/10">
                {mission_config.crew_count} Crew Configured
              </span>
            </div>
            <p className="text-sm text-[#E5E5E4] max-w-3xl">
              Monitor ration inventory, multi-category remaining-supply projections, shelf-life safety, potable water reserves, and individual nutritional targets connected to Health Assessment.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setShowAddForm(!showAddForm)}
              className="mc-btn-primary text-xs flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Food Item
            </button>
            <button
              onClick={() => setActiveSubTab('consume_resupply')}
              className="mc-btn-secondary text-xs flex items-center gap-1.5"
            >
              <Utensils className="w-3.5 h-3.5 text-[#A5D8FF]" />
              Record Meal / Resupply
            </button>
          </div>
        </div>

        {/* Sub-navigation bar */}
        <div className="flex flex-wrap items-center gap-2 mt-5 pt-4 border-t border-[#222638]">
          {[
            { id: 'dashboard', label: 'Inventory Dashboard', icon: Package },
            { id: 'consume_resupply', label: 'Record Meal & Resupply', icon: Utensils },
            { id: 'projections', label: 'Remaining Supply Estimator', icon: Calculator },
            { id: 'nutrition', label: 'Nutritional Monitoring', icon: Droplets },
            { id: 'history', label: `Alerts (${food_alerts.length}) & Audit History`, icon: History },
          ].map((t) => {
            const Icon = t.icon;
            const active = activeSubTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActiveSubTab(t.id as any)}
                className={`px-3.5 py-2 rounded-full text-xs font-medium transition-all flex items-center gap-1.5 ${
                  active
                    ? 'bg-[#EEF0F6] text-[#040404] font-semibold'
                    : 'bg-white/[0.04] text-[#E5E5E4] hover:bg-white/[0.08]'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Feedback Banner */}
      {bannerMsg && (
        <div
          className={`mc-card p-4 flex items-center justify-between text-sm ${
            bannerMsg.type === 'ok'
              ? 'border-emerald-500/40 text-emerald-200'
              : 'border-rose-500/40 text-rose-200'
          }`}
        >
          <div className="flex items-center gap-2.5">
            {bannerMsg.type === 'ok' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{bannerMsg.text}</span>
          </div>
          <button
            onClick={() => setBannerMsg(null)}
            className="text-xs text-[#8E95A8] hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Top KPI Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="mc-card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-[#E5E5E4]">Primary Meal Portions</span>
            <Package className="w-4 h-4 text-[#A5D8FF]" />
          </div>
          <div className="text-2xl font-bold text-[#FAF9FA] tabular-nums">
            {summary.available_meal_portions.toLocaleString()} portions
          </div>
          <p className="text-xs text-[#8E95A8] mt-1">
            Across {summary.total_food_items} tracked inventory lots ({(summary.total_kcal_available / 1000).toFixed(0)}k kcal total)
          </p>
        </div>

        <div className="mc-card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-[#E5E5E4]">Projected Meal Duration</span>
            <Clock className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-[#FAF9FA] tabular-nums">
            ~{summary.estimated_meal_supply_days} Sols
          </div>
          <p className="text-xs text-[#8E95E4] text-[#8E95A8] mt-1">
            Projection to Sol {primary_meal_projection.projected_depletion_sol} (Next resupply: Sol {mission_config.next_resupply_sol})
          </p>
        </div>

        <div className="mc-card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-[#E5E5E4]">Potable Water Reserve</span>
            <Droplets className="w-4 h-4 text-[#A5D8FF]" />
          </div>
          <div className="text-2xl font-bold text-[#FAF9FA] tabular-nums">
            {summary.potable_water_liters} L (~{summary.estimated_water_supply_days} Sols)
          </div>
          <p className="text-xs text-[#8E95A8] mt-1">
            Today logged: {summary.daily_water_consumption_ml} mL · Warning threshold: {mission_config.water_warning_threshold_liters} L
          </p>
        </div>

        <div className="mc-card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-[#E5E5E4]">Stock &amp; Expiry Watch</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-[#FAF9FA] tabular-nums">
            {summary.low_stock_count} Low · {summary.expiring_soon_count} Expiring
          </div>
          <p className="text-xs text-[#8E95A8] mt-1">
            Sol {mission_config.current_mission_sol} intake: {summary.daily_food_consumption_kcal.toFixed(0)} / {nutrition_overview.targets.calories_target_kcal.toFixed(0)} kcal
          </p>
        </div>
      </div>

      {/* Add Food Item Form Drawer */}
      {showAddForm && (
        <div className="mc-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-[#FAF9FA]">
              Add New Food or Life-Support Item
            </h2>
            <button
              onClick={() => setShowAddForm(false)}
              className="text-xs text-[#8E95A8] hover:text-white"
            >
              Close
            </button>
          </div>
          <form onSubmit={handleAddFoodItem} className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div>
              <label className="block text-[#E5E5E4] mb-1">Food Name *</label>
              <input
                type="text"
                required
                value={newItem.name}
                onChange={(e) => setNewItem({ ...newItem, name: e.target.value })}
                placeholder="e.g., Freeze-Dried Beef Stroganoff Pouch"
                className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
              />
            </div>
            <div>
              <label className="block text-[#E5E5E4] mb-1">Category</label>
              <select
                value={newItem.category}
                onChange={(e) => setNewItem({ ...newItem, category: e.target.value })}
                className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
              >
                {FOOD_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[#E5E5E4] mb-1">Quantity Available</label>
                <input
                  type="number"
                  step="0.5"
                  min="0"
                  value={newItem.quantity}
                  onChange={(e) => setNewItem({ ...newItem, quantity: Number(e.target.value) })}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
              <div>
                <label className="block text-[#E5E5E4] mb-1">Unit</label>
                <input
                  type="text"
                  value={newItem.unit}
                  onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[#E5E5E4] mb-1">Calories / Serving (kcal)</label>
                <input
                  type="number"
                  min="0"
                  value={newItem.calories_per_serving}
                  onChange={(e) =>
                    setNewItem({ ...newItem, calories_per_serving: Number(e.target.value) })
                  }
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
              <div>
                <label className="block text-[#E5E5E4] mb-1">Protein (g)</label>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={newItem.protein_g}
                  onChange={(e) => setNewItem({ ...newItem, protein_g: Number(e.target.value) })}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[#E5E5E4] mb-1">Carbohydrates (g)</label>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={newItem.carbs_g}
                  onChange={(e) => setNewItem({ ...newItem, carbs_g: Number(e.target.value) })}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
              <div>
                <label className="block text-[#E5E5E4] mb-1">Fat (g)</label>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={newItem.fat_g}
                  onChange={(e) => setNewItem({ ...newItem, fat_g: Number(e.target.value) })}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[#E5E5E4] mb-1">Expiry Sol</label>
                <input
                  type="number"
                  value={newItem.expiry_sol}
                  onChange={(e) => setNewItem({ ...newItem, expiry_sol: Number(e.target.value) })}
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
              <div>
                <label className="block text-[#E5E5E4] mb-1">Low-Stock Threshold</label>
                <input
                  type="number"
                  value={newItem.min_threshold}
                  onChange={(e) =>
                    setNewItem({ ...newItem, min_threshold: Number(e.target.value) })
                  }
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
            </div>

            <div>
              <label className="block text-[#E5E5E4] mb-1">Storage Requirements</label>
              <input
                type="text"
                value={newItem.storage_requirements}
                onChange={(e) =>
                  setNewItem({ ...newItem, storage_requirements: e.target.value })
                }
                className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
              />
            </div>

            <div>
              <label className="block text-[#E5E5E4] mb-1">Food Source</label>
              <input
                type="text"
                value={newItem.food_source}
                onChange={(e) => setNewItem({ ...newItem, food_source: e.target.value })}
                className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
              />
            </div>

            <div className="flex items-end justify-end gap-2">
              <label className="flex items-center gap-2 text-[#E5E5E4] mr-auto py-2">
                <input
                  type="checkbox"
                  checked={newItem.nutrition_complete}
                  onChange={(e) =>
                    setNewItem({ ...newItem, nutrition_complete: e.target.checked })
                  }
                />
                Complete Food-Label Nutrition
              </label>
              <button type="submit" disabled={busy} className="mc-btn-primary px-4 py-2">
                Save Item to Inventory
              </button>
            </div>
          </form>
        </div>
      )}

      {/* SUB-TAB 1: INVENTORY DASHBOARD */}
      {activeSubTab === 'dashboard' && (
        <div className="space-y-6">
          {/* Active Food & Supply Alerts Strip */}
          {food_alerts.length > 0 && (
            <div className="mc-card p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-base font-semibold text-[#FAF9FA] flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  Active Food, Water &amp; Expiry Alerts ({food_alerts.length})
                </h2>
                <span className="text-xs text-[#8E95A8]">
                  Integrated with TARSCARE Notification System · Never recommends expired rations
                </span>
              </div>
              <div className="divide-y divide-[#222638]">
                {food_alerts.map((al) => (
                  <div
                    key={al.alert_uid}
                    className="py-3 first:pt-0 last:pb-0 flex flex-col md:flex-row md:items-center md:justify-between gap-2 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`mc-pill ${
                            al.severity === 'CRITICAL'
                              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                              : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                          }`}
                        >
                          {al.severity} · {al.alert_type}
                        </span>
                        <span className="font-semibold text-[#FAF9FA]">
                          {al.affected_item_name}
                        </span>
                        <span className="text-[#8E95A8]">
                          ({al.current_quantity} {al.unit})
                        </span>
                      </div>
                      <p className="text-[#E5E5E4]">{al.recommended_action}</p>
                    </div>
                    <span className="text-[11px] text-[#8E95A8] shrink-0">
                      {al.timestamp.slice(0, 16).replace('T', ' ')} UTC
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Inventory Filter & Table */}
          <div className="mc-card p-6">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
              <div>
                <h2 className="text-lg font-semibold text-[#FAF9FA]">
                  Galley &amp; Life-Support Inventory Lots
                </h2>
                <p className="text-xs text-[#8E95A8]">{summary.provenance_note}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                >
                  <option value="ALL">All Categories ({items.length})</option>
                  {FOOD_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="AVAILABLE">Available</option>
                  <option value="RUNNING_LOW">Running Low</option>
                  <option value="EXPIRING_SOON">Expiring Soon</option>
                  <option value="CRITICAL">Critical</option>
                  <option value="EXPIRED">Expired</option>
                </select>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#222638] text-[#8E95A8]">
                    <th className="py-2.5 pr-3 font-medium">Food Item &amp; Source</th>
                    <th className="py-2.5 px-3 font-medium">Category &amp; Storage</th>
                    <th className="py-2.5 px-3 font-medium">Available Quantity</th>
                    <th className="py-2.5 px-3 font-medium">Macros / Serving</th>
                    <th className="py-2.5 px-3 font-medium">Expiry &amp; Shelf Life</th>
                    <th className="py-2.5 px-3 font-medium">Status</th>
                    <th className="py-2.5 pl-3 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#222638]">
                  {filteredItems.map((item) => {
                    const isEditing = editingUid === item.item_uid;
                    return (
                      <tr key={item.item_uid} className="hover:bg-white/[0.02]">
                        <td className="py-3.5 pr-3 align-top">
                          <div className="font-semibold text-[#FAF9FA]">{item.name}</div>
                          <div className="text-[11px] text-[#8E95A8] mt-0.5">
                            {item.food_source} · Provenance: {item.provenance}
                          </div>
                          {!item.nutrition_complete && (
                            <span className="inline-block mt-1 text-[11px] text-amber-300">
                              Estimated micronutrient label (fresh harvest)
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-3 align-top">
                          <div className="text-[#E5E5E4]">{item.category}</div>
                          <div className="text-[11px] text-[#8E95A8] mt-0.5">
                            {item.bay_location} · {item.storage_requirements}
                          </div>
                        </td>
                        <td className="py-3.5 px-3 align-top tabular-nums">
                          {isEditing ? (
                            <div className="space-y-1.5">
                              <input
                                type="number"
                                step="0.5"
                                min="0"
                                value={editQty}
                                onChange={(e) => setEditQty(Number(e.target.value))}
                                className="w-24 rounded bg-[#0B0D1A] border border-[#A5D8FF] px-2 py-1 text-[#FAF9FA]"
                              />
                              <input
                                type="text"
                                value={editNotes}
                                onChange={(e) => setEditNotes(e.target.value)}
                                placeholder="Audit note..."
                                className="w-36 block rounded bg-[#0B0D1A] border border-[#222638] px-2 py-1 text-[#FAF9FA]"
                              />
                            </div>
                          ) : (
                            <>
                              <div className="font-semibold text-[#FAF9FA]">
                                {item.quantity} {item.unit}
                              </div>
                              <div className="text-[11px] text-[#8E95A8]">
                                Initial: {item.initial_quantity} · Low &le; {item.min_threshold}
                              </div>
                            </>
                          )}
                        </td>
                        <td className="py-3.5 px-3 align-top tabular-nums">
                          <div className="text-[#FAF9FA] font-medium">
                            {item.calories_per_serving} kcal
                          </div>
                          <div className="text-[11px] text-[#8E95A8]">
                            P {item.protein_g}g · C {item.carbs_g}g · F {item.fat_g}g
                          </div>
                          {item.water_ml_per_serving > 0 && (
                            <div className="text-[11px] text-[#A5D8FF]">
                              Hydration: {item.water_ml_per_serving} mL
                            </div>
                          )}
                        </td>
                        <td className="py-3.5 px-3 align-top tabular-nums">
                          <div className="text-[#E5E5E4]">
                            Sol {item.expiry_sol} ({item.expiry_date})
                          </div>
                          <div
                            className={`text-[11px] ${
                              item.sols_until_expiry <= 14 ? 'text-amber-300 font-medium' : 'text-[#8E95A8]'
                            }`}
                          >
                            {item.sols_until_expiry >= 0
                              ? `${item.sols_until_expiry} Sols remaining`
                              : `Expired ${Math.abs(item.sols_until_expiry)} Sols ago`}
                          </div>
                        </td>
                        <td className="py-3.5 px-3 align-top">{statusBadge(item.status)}</td>
                        <td className="py-3.5 pl-3 align-top text-right">
                          {isEditing ? (
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => handleSaveEditQuantity(item)}
                                disabled={busy}
                                className="mc-btn-primary px-2.5 py-1 text-[11px]"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingUid(null)}
                                className="mc-btn-secondary px-2 py-1 text-[11px]"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center justify-end gap-1.5">
                              <button
                                onClick={() => {
                                  setEditingUid(item.item_uid);
                                  setEditQty(item.quantity);
                                  setEditNotes(item.notes);
                                }}
                                title="Update Quantity"
                                className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.1] text-[#E5E5E4]"
                              >
                                <Edit3 className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => handleRemoveItem(item)}
                                title="Remove / Dispose Item"
                                className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* SUB-TAB 2: RECORD MEAL CONSUMPTION & RESUPPLY */}
      {activeSubTab === 'consume_resupply' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Record Meal Consumption */}
          <div className="mc-card p-6">
            <h2 className="text-lg font-semibold text-[#FAF9FA] mb-1">
              Record Meal &amp; Hydration Consumption
            </h2>
            <p className="text-xs text-[#8E95A8] mb-4">
              Deducts consumed portions from galley inventory and updates {state.astronaut.name}&apos;s Sol {mission_config.current_mission_sol} nutritional profile. Expired items are automatically blocked for crew safety.
            </p>
            <form onSubmit={handleRecordConsumption} className="space-y-4 text-xs">
              <div>
                <label className="block text-[#E5E5E4] mb-1">Select Food / Ration Item</label>
                <select
                  value={consumeForm.food_item_uid}
                  onChange={(e) =>
                    setConsumeForm({ ...consumeForm, food_item_uid: e.target.value })
                  }
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                >
                  {items.map((i) => (
                    <option key={i.item_uid} value={i.item_uid}>
                      {i.name} ({i.quantity} {i.unit} avail · {i.calories_per_serving} kcal · {i.status})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Meal Slot</label>
                  <select
                    value={consumeForm.meal_type}
                    onChange={(e) =>
                      setConsumeForm({ ...consumeForm, meal_type: e.target.value })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  >
                    <option value="Breakfast">Breakfast</option>
                    <option value="Lunch">Lunch</option>
                    <option value="Dinner">Dinner</option>
                    <option value="Snack / EVA Ration">Snack / EVA Ration</option>
                    <option value="Hydration">Hydration</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Quantity Consumed</label>
                  <input
                    type="number"
                    step="0.5"
                    min="0.5"
                    value={consumeForm.quantity_consumed}
                    onChange={(e) =>
                      setConsumeForm({
                        ...consumeForm,
                        quantity_consumed: Number(e.target.value),
                      })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  />
                </div>
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Extra Drinking Water (mL)</label>
                  <input
                    type="number"
                    step="50"
                    min="0"
                    value={consumeForm.extra_water_ml}
                    onChange={(e) =>
                      setConsumeForm({
                        ...consumeForm,
                        extra_water_ml: Number(e.target.value),
                      })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[#E5E5E4] mb-1">Meal / Crew Notes (Optional)</label>
                <input
                  type="text"
                  value={consumeForm.notes}
                  onChange={(e) => setConsumeForm({ ...consumeForm, notes: e.target.value })}
                  placeholder="e.g., Post-EVA recovery meal in Galley G1"
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>

              <button type="submit" disabled={busy} className="mc-btn-primary w-full py-2.5">
                Log Meal &amp; Deduct Inventory
              </button>
            </form>
          </div>

          {/* Record Resupply or Habitat Veggie Harvest */}
          <div className="mc-card p-6">
            <h2 className="text-lg font-semibold text-[#FAF9FA] mb-1">
              Record Resupply Delivery or Veggie Harvest
            </h2>
            <p className="text-xs text-[#8E95A8] mb-4">
              Log cargo pallet transfers, hydroponic Veggie chamber harvests, or ECLSS/ISRU potable water batch additions.
            </p>
            <form onSubmit={handleRecordResupply} className="space-y-4 text-xs">
              <div>
                <label className="block text-[#E5E5E4] mb-1">Target Inventory Item</label>
                <select
                  value={resupplyForm.food_item_uid}
                  onChange={(e) =>
                    setResupplyForm({ ...resupplyForm, food_item_uid: e.target.value })
                  }
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                >
                  {items.map((i) => (
                    <option key={i.item_uid} value={i.item_uid}>
                      {i.name} (Current: {i.quantity} {i.unit})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Resupply Event Type</label>
                  <select
                    value={resupplyForm.event_type}
                    onChange={(e) =>
                      setResupplyForm({ ...resupplyForm, event_type: e.target.value })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  >
                    <option value="RESUPPLY_DELIVERY">Pre-Positioned Cargo Transfer</option>
                    <option value="VEGGIE_HARVEST">Veggie Chamber Fresh Harvest</option>
                    <option value="ECLSS_WATER_RECOVERY">ECLSS / ISRU Water Recovery</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Quantity Added</label>
                  <input
                    type="number"
                    step="1"
                    min="0.5"
                    value={resupplyForm.quantity_added}
                    onChange={(e) =>
                      setResupplyForm({
                        ...resupplyForm,
                        quantity_added: Number(e.target.value),
                      })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Source Module / Batch</label>
                  <input
                    type="text"
                    value={resupplyForm.source}
                    onChange={(e) =>
                      setResupplyForm({ ...resupplyForm, source: e.target.value })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  />
                </div>
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Authorised By</label>
                  <input
                    type="text"
                    value={resupplyForm.authorised_by}
                    onChange={(e) =>
                      setResupplyForm({ ...resupplyForm, authorised_by: e.target.value })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[#E5E5E4] mb-1">Inspection / Batch Notes</label>
                <input
                  type="text"
                  value={resupplyForm.notes}
                  onChange={(e) => setResupplyForm({ ...resupplyForm, notes: e.target.value })}
                  placeholder="Seal integrity & microbiological check verified"
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>

              <button type="submit" disabled={busy} className="mc-btn-secondary w-full py-2.5">
                Record Resupply &amp; Update Stock
              </button>
            </form>
          </div>
        </div>
      )}

      {/* SUB-TAB 3: REMAINING SUPPLY ESTIMATION ENGINE */}
      {activeSubTab === 'projections' && (
        <div className="space-y-6">
          {/* Category-by-Category Projection Table */}
          <div className="mc-card p-6">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-4">
              <div>
                <h2 className="text-lg font-semibold text-[#FAF9FA]">
                  Multi-Category Remaining Supply Projections
                </h2>
                <p className="text-xs text-[#8E95A8]">
                  {primary_meal_projection.projection_disclaimer} Different food categories have distinct consumption patterns and are never collapsed into a single misleading figure.
                </p>
              </div>
              <span className="mc-pill bg-[#A5D8FF]/15 text-[#A5D8FF] border border-[#A5D8FF]/30">
                Planned End: Sol {mission_config.planned_mission_end_sol} · Next Resupply: Sol {mission_config.next_resupply_sol}
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#222638] text-[#8E95A8]">
                    <th className="py-2.5 pr-3 font-medium">Supply Category</th>
                    <th className="py-2.5 px-3 font-medium">Available Stock</th>
                    <th className="py-2.5 px-3 font-medium">Crew Daily Consumption Rate</th>
                    <th className="py-2.5 px-3 font-medium">Consumption Trend</th>
                    <th className="py-2.5 px-3 font-medium">Estimated Remaining Days</th>
                    <th className="py-2.5 px-3 font-medium">Projected Depletion</th>
                    <th className="py-2.5 pl-3 font-medium text-right">Projection Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#222638]">
                  {category_projections.map((cp) => (
                    <tr key={cp.category} className="hover:bg-white/[0.02]">
                      <td className="py-3 pr-3 font-semibold text-[#FAF9FA]">
                        {cp.category}
                        <span className="text-[#8E95A8] font-normal ml-1.5">
                          ({cp.item_count} lot{cp.item_count > 1 ? 's' : ''})
                        </span>
                      </td>
                      <td className="py-3 px-3 tabular-nums text-[#E5E5E4]">
                        {cp.available_quantity} {cp.unit}
                      </td>
                      <td className="py-3 px-3 tabular-nums text-[#E5E5E4]">
                        {cp.effective_daily_crew_rate} {cp.unit}/Sol
                        <span className="block text-[11px] text-[#8E95A8]">
                          Configured: {cp.configured_daily_crew_rate} {cp.unit}/Sol
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <span className="mc-pill bg-white/5 text-[#E5E5E4]">
                          {cp.consumption_trend.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="py-3 px-3 tabular-nums font-semibold text-[#FAF9FA]">
                        ~{cp.estimated_remaining_days} Sols (Projection)
                      </td>
                      <td className="py-3 px-3 tabular-nums text-[#E5E5E4]">
                        Sol {cp.projected_depletion_sol} ({cp.projected_depletion_date})
                      </td>
                      <td className="py-3 pl-3 text-right">
                        <span
                          className={`mc-pill ${
                            cp.status === 'CRITICAL'
                              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                              : cp.status === 'WARNING'
                              ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                              : 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                          }`}
                        >
                          {cp.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Interactive Supply Duration Calculator */}
          <div className="mc-card p-6">
            <h2 className="text-lg font-semibold text-[#FAF9FA] mb-1">
              Interactive Ration Duration Estimator
            </h2>
            <p className="text-xs text-[#8E95A8] mb-4">
              Test mission ration scenarios (for example: 120 meal portions across 2 astronauts at 3 portions per astronaut per day = 20.0 days remaining).
            </p>
            <form
              onSubmit={handleRunProjectionCalc}
              className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end text-xs"
            >
              <div>
                <label className="block text-[#E5E5E4] mb-1">Total Meal Portions Remaining</label>
                <input
                  type="number"
                  step="1"
                  min="0"
                  value={calcInput.total_portions}
                  onChange={(e) =>
                    setCalcInput({ ...calcInput, total_portions: Number(e.target.value) })
                  }
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
              <div>
                <label className="block text-[#E5E5E4] mb-1">Number of Astronauts</label>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={calcInput.astronaut_count}
                  onChange={(e) =>
                    setCalcInput({ ...calcInput, astronaut_count: Number(e.target.value) })
                  }
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
              <div>
                <label className="block text-[#E5E5E4] mb-1">Portions / Astronaut / Day</label>
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  value={calcInput.portions_per_astronaut_per_day}
                  onChange={(e) =>
                    setCalcInput({
                      ...calcInput,
                      portions_per_astronaut_per_day: Number(e.target.value),
                    })
                  }
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-2 text-[#FAF9FA]"
                />
              </div>
              <div className="flex items-center gap-2">
                <button type="submit" disabled={busy} className="mc-btn-primary py-2 px-4 w-full">
                  Calculate Projection
                </button>
              </div>
            </form>

            {calcResult && (
              <div className="mt-4 pt-4 border-t border-[#222638] grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
                <div>
                  <span className="text-[#8E95A8] block">Estimated Remaining Duration</span>
                  <span className="text-xl font-bold text-[#FAF9FA] tabular-nums">
                    {calcResult.estimated_remaining_days} Days (Sols)
                  </span>
                </div>
                <div>
                  <span className="text-[#8E95A8] block">Daily Crew Consumption</span>
                  <span className="text-base font-semibold text-[#E5E5E4] tabular-nums">
                    {calcResult.daily_crew_consumption_rate} portions / day
                  </span>
                </div>
                <div>
                  <span className="text-[#8E95A8] block">Projected Depletion</span>
                  <span className="text-base font-semibold text-[#E5E5E4] tabular-nums">
                    Sol {calcResult.projected_depletion_sol} ({calcResult.projected_depletion_date})
                  </span>
                </div>
                <div>
                  <span className="text-[#8E95A8] block">Projection Notice</span>
                  <span className="text-[#A5D8FF]">{calcResult.projection_disclaimer}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUB-TAB 4: NUTRITIONAL MONITORING & PER-ASTRONAUT TARGETS */}
      {activeSubTab === 'nutrition' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 mc-card p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-[#FAF9FA]">
                  Sol {nutrition_overview.mission_day} Nutritional Intake — {state.astronaut.name}
                </h2>
                <p className="text-xs text-[#8E95A8]">
                  Connected to TARSCARE Health Assessment &amp; Gravity Countermeasure Readiness ({state.astronaut.role})
                </p>
              </div>
              {onNavigate && (
                <button
                  onClick={() => onNavigate('hazards')}
                  className="mc-btn-secondary text-xs flex items-center gap-1"
                >
                  View 5-Hazard Assessment
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Progress Bars */}
            <div className="space-y-3.5 text-xs">
              {[
                {
                  label: 'Daily Energy Intake',
                  rec: `${nutrition_overview.recorded.calories_kcal.toFixed(0)} kcal`,
                  tgt: `${nutrition_overview.targets.calories_target_kcal.toFixed(0)} kcal`,
                  pct: nutrition_overview.progress_pct.calories,
                },
                {
                  label: 'Protein (Muscle & Bone Retention)',
                  rec: `${nutrition_overview.recorded.protein_g.toFixed(1)} g`,
                  tgt: `${nutrition_overview.targets.protein_target_g.toFixed(0)} g`,
                  pct: nutrition_overview.progress_pct.protein,
                },
                {
                  label: 'Carbohydrates (EVA & CNS Fuel)',
                  rec: `${nutrition_overview.recorded.carbs_g.toFixed(1)} g`,
                  tgt: `${nutrition_overview.targets.carbs_target_g.toFixed(0)} g`,
                  pct: nutrition_overview.progress_pct.carbs,
                },
                {
                  label: 'Dietary Fat',
                  rec: `${nutrition_overview.recorded.fat_g.toFixed(1)} g`,
                  tgt: `${nutrition_overview.targets.fat_target_g.toFixed(0)} g`,
                  pct: nutrition_overview.progress_pct.fat,
                },
                {
                  label: 'Hydration (Meal + Beverage Water)',
                  rec: `${nutrition_overview.recorded.water_ml.toFixed(0)} mL`,
                  tgt: `${nutrition_overview.targets.water_target_ml.toFixed(0)} mL`,
                  pct: nutrition_overview.progress_pct.water,
                },
              ].map((m) => (
                <div key={m.label} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-[#E5E5E4]">{m.label}</span>
                    <span className="tabular-nums text-[#FAF9FA]">
                      {m.rec} / {m.tgt} ({m.pct.toFixed(0)}%)
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-[#0B0D1A] overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        m.pct < 70
                          ? 'bg-amber-400'
                          : m.pct > 120
                          ? 'bg-[#A5D8FF]'
                          : 'bg-emerald-400'
                      }`}
                      style={{ width: `${Math.min(100, m.pct)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* Micronutrients Summary */}
            <div className="pt-4 border-t border-[#222638]">
              <h3 className="text-sm font-semibold text-[#FAF9FA] mb-2">
                Tracked Micronutrients (Sol {nutrition_overview.mission_day})
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                <div className="p-3 rounded-lg bg-[#0B0D1A]/60">
                  <span className="text-[#8E95A8] block">Vitamin D3</span>
                  <span className="font-semibold text-[#FAF9FA] tabular-nums">
                    {nutrition_overview.recorded.micronutrients.vitamin_d_iu || 0} /{' '}
                    {nutrition_overview.targets.vitamin_d_target_iu} IU
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-[#0B0D1A]/60">
                  <span className="text-[#8E95A8] block">Calcium</span>
                  <span className="font-semibold text-[#FAF9FA] tabular-nums">
                    {nutrition_overview.recorded.micronutrients.calcium_mg || 0} /{' '}
                    {nutrition_overview.targets.calcium_target_mg} mg
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-[#0B0D1A]/60">
                  <span className="text-[#8E95A8] block">Vitamin C / Potassium</span>
                  <span className="font-semibold text-[#FAF9FA] tabular-nums">
                    {nutrition_overview.recorded.micronutrients.vitamin_c_mg || 0} mg ·{' '}
                    {nutrition_overview.recorded.micronutrients.potassium_mg || 0} mg
                  </span>
                </div>
              </div>
            </div>

            {/* Target Comparison Explanations */}
            <div className="pt-4 border-t border-[#222638] space-y-2 text-xs">
              <h3 className="text-sm font-semibold text-[#FAF9FA]">
                Mission Target Comparison &amp; Guidance
              </h3>
              {nutrition_overview.explanations.map((exp, i) => (
                <p key={i} className="text-[#E5E5E4]">
                  • {exp}
                </p>
              ))}
              <p className="text-[11px] text-[#8E95A8] pt-1">
                {nutrition_overview.safety_disclaimer}
              </p>
            </div>
          </div>

          {/* Configurable Individual Astronaut Targets */}
          <div className="mc-card p-6">
            <h2 className="text-base font-semibold text-[#FAF9FA] mb-1 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-[#A5D8FF]" />
              Configure Personal Targets
            </h2>
            <p className="text-xs text-[#8E95A8] mb-4">
              Nutritional requirements vary by astronaut body mass, EVA workload, and ARED countermeasure schedule.
            </p>
            <form onSubmit={handleSaveNutritionTargets} className="space-y-3 text-xs">
              <div>
                <label className="block text-[#E5E5E4] mb-1">Daily Calorie Target (kcal)</label>
                <input
                  type="number"
                  value={targetForm.calories_target_kcal}
                  onChange={(e) =>
                    setTargetForm({ ...targetForm, calories_target_kcal: Number(e.target.value) })
                  }
                  className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Protein Target (g)</label>
                  <input
                    type="number"
                    value={targetForm.protein_target_g}
                    onChange={(e) =>
                      setTargetForm({ ...targetForm, protein_target_g: Number(e.target.value) })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                  />
                </div>
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Water Target (mL)</label>
                  <input
                    type="number"
                    value={targetForm.water_target_ml}
                    onChange={(e) =>
                      setTargetForm({ ...targetForm, water_target_ml: Number(e.target.value) })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Carbs Target (g)</label>
                  <input
                    type="number"
                    value={targetForm.carbs_target_g}
                    onChange={(e) =>
                      setTargetForm({ ...targetForm, carbs_target_g: Number(e.target.value) })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                  />
                </div>
                <div>
                  <label className="block text-[#E5E5E4] mb-1">Fat Target (g)</label>
                  <input
                    type="number"
                    value={targetForm.fat_target_g}
                    onChange={(e) =>
                      setTargetForm({ ...targetForm, fat_target_g: Number(e.target.value) })
                    }
                    className="w-full rounded-lg bg-[#0B0D1A] border border-[#222638] px-3 py-1.5 text-[#FAF9FA]"
                  />
                </div>
              </div>
              <button type="submit" disabled={busy} className="mc-btn-primary w-full py-2 mt-2">
                Save {state.astronaut.name}&apos;s Targets
              </button>
            </form>
          </div>
        </div>
      )}

      {/* SUB-TAB 5: ALERTS & CONSUMPTION / RESUPPLY HISTORY */}
      {activeSubTab === 'history' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="mc-card p-6">
            <h2 className="text-base font-semibold text-[#FAF9FA] mb-3">
              Recent Meal &amp; Hydration Consumption Log ({consumption_history.length})
            </h2>
            <div className="divide-y divide-[#222638] max-h-96 overflow-y-auto text-xs">
              {consumption_history.map((c) => (
                <div key={c.consumption_uid} className="py-2.5 flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-[#FAF9FA]">
                      Sol {c.mission_day} · {c.meal_type}: {c.food_name}
                    </div>
                    <div className="text-[#8E95A8]">
                      {c.quantity_consumed} {c.unit} · {c.calories} kcal (P {c.protein_g}g, C {c.carbs_g}g, F {c.fat_g}g) · Water {c.water_ml} mL
                    </div>
                    {c.is_estimated_nutrition && (
                      <span className="text-[11px] text-amber-300">
                        Includes estimated harvest label values
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-[#8E95A8] shrink-0">{c.provenance}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mc-card p-6">
            <h2 className="text-base font-semibold text-[#FAF9FA] mb-3">
              Resupply, Harvest &amp; Galley Audit History ({resupply_history.length})
            </h2>
            <div className="divide-y divide-[#222638] max-h-96 overflow-y-auto text-xs">
              {resupply_history.map((r) => (
                <div key={r.resupply_uid} className="py-2.5 flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-[#FAF9FA]">
                      Sol {r.mission_day} · {r.event_type}: {r.food_name}
                    </div>
                    <div className="text-[#8E95A8]">
                      Delta: {r.quantity_delta > 0 ? `+${r.quantity_delta}` : r.quantity_delta} {r.unit} &rarr; Stock: {r.quantity_after} {r.unit} · {r.source}
                    </div>
                    {r.notes && <div className="text-[11px] text-[#E5E5E4] mt-0.5">{r.notes}</div>}
                  </div>
                  <span className="text-[11px] text-[#8E95A8] shrink-0">{r.authorised_by}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
