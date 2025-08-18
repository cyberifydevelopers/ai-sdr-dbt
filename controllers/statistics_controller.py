from collections import defaultdict
from fastapi import APIRouter, Depends
from typing import Annotated, Dict
# from helpers.get_sales_manager import get_sales_manager
from helpers.get_user_admin import get_user_admin
from models.call_log import CallLog
from models.documents import Documents
from models.purchased_numbers import PurchasedNumber
from models.auth import User
from models.lead import Lead
from models.file import File
from models.assistant import Assistant
# from models.documents import Documents
from helpers.token_helper import get_current_user
from helpers.get_admin import get_admin
from fastapi import  Query
from typing import List
from datetime import datetime, timedelta
from pydantic import BaseModel
# from models.company import Company
from controllers.lead_controller import count_leads_in_csv
router = APIRouter()

class UserStats(BaseModel):
    date: str
    count: int

@router.get("/statistics")
async def get_statistics(user: Annotated[User, Depends(get_current_user)]):
    return {
        "leads": await Lead.filter(file__user_id=user.id).count(),
        "files": await File.filter(user_id=user.id).count(),
        "assistants": await Assistant.filter(user_id=user.id).count(),
        "phone_numbers": await PurchasedNumber.filter(user_id=user.id).count(),
        "knowledge_base": await Documents.filter(user_id=user.id).count(),
        # "knowledge_base": 0,
    }



# @router.get("/statistics/{company_id}")
# async def get_statistics(
#     user: Annotated[User, Depends(get_admin)],
#     company_id: int
# ):
#     get_company = await Company.get(id=company_id)

#     users = await User.filter(company=get_company).all()

#     assistants_count = 0
#     calllogs_count = 0
#     phonenumbers_count = 0
#     for user in users:
#         assistants_count += await Assistant.filter(user_id=user.id).count()
#         calllogs_count += await CallLog.filter(user_id=user.id).count()
#         phonenumbers_count += await PurchasedNumber.filter(user_id=user.id).count() 
#     return {
#         "success": True,
#         "assistants": assistants_count,
#         "calllogs": calllogs_count,
#         "phonenumbers": phonenumbers_count,
#         "users": len(users), 
#     }





# @router.get("/admin/statistics")
# async def admin_stats(user: Annotated[User, Depends(get_admin)]):
#     return{
#         "leads": await Lead.filter().count(),
#         "files": await File.filter().count(),
#         "users": await User.filter().count(),
#         "assistants": await Assistant.filter().count()
#     }



# @router.get("/manager-statistics")
# async def get_statistics(user: Annotated[User, Depends(get_sales_manager)],
# ):
#     return {
#         "sales_person": await User.filter(role='sales_person').count(),
#     }
# @router.get("/admin/users-stats")
# async def admin_stats(
#     user: Annotated[User, Depends(get_admin)],
#     period: str = Query("30d", description="Time period: 30d, 3m, 6m"),
# ):
#     today = datetime.utcnow()

#     if period == "3m":
#         start_date = today - timedelta(days=90)
#     elif period == "6m":
#         start_date = today - timedelta(days=180)
#     else:
#         start_date = today - timedelta(days=30)

#     users = await User.filter(created_at__gte=start_date).values("created_at")

#     user_counts: Dict[str, int] = defaultdict(int)
#     for user in users:
#         date_str = user["created_at"].strftime("%Y-%m-%d") 
#         user_counts[date_str] += 1

#     return [{"date": date, "count": count} for date, count in sorted(user_counts.items())]


# @router.get("/admin/pl-report")
# async def pl_report(
#     user: Annotated[User, Depends(get_admin)],
#     period: str = Query("30d", description="Time period: 30d, 3m, 6m"),
# ):
#     today = datetime.utcnow()

#     if period == "3m":
#         start_date = today - timedelta(days=90)
#     elif period == "6m":
#         start_date = today - timedelta(days=180)
#     else:
#         start_date = today - timedelta(days=30)

#     total_call_cost = await CallLog.filter(call_started_at__gte=start_date)
#     total_purchased_numbers = await PurchasedNumber.filter(created_at__gte=start_date)

#     total_call_cost_value = sum(call_log.cost for call_log in total_call_cost if call_log.cost is not None)


#     total_purchased_number_count = len(total_purchased_numbers)
#     total_purchased_number_cost = total_purchased_number_count * 1 

#     total_transfer_calls = sum(1 for call_log in total_call_cost if call_log.is_transferred)
#     total_call_profit = total_transfer_calls * 10 

#     total_purchased_number_profit = total_purchased_number_count * 5

#     report = {
#         "total_call_cost": total_call_cost_value,
#         "total_purchased_number_cost": total_purchased_number_cost,
#         "total_call_profit": total_call_profit,
#         "total_purchased_number_profit": total_purchased_number_profit,
#         "net_profit": total_call_profit + total_purchased_number_profit - total_call_cost_value - total_purchased_number_cost,
#     }

#     return report
